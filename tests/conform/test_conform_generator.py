"""Conform: the staged Products model built by dbt from the generated raw and conform models (AC6, AC7, EC5)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
import yaml

from harness import (
    CONTRACT,
    CONTRACT_PATH,
    REPO,
    SNAKE,
    SUBCATEGORIES,
    SUBCATEGORIES_CONTRACT_PATH,
    epoch_us,
    load_id,
    product,
    q,
    require,
    subcategory,
    write_load,
)

PLATFORM = {
    "_dlt__load_id",
    "_dlt__id",
    "_dlt__extracted_at",
    "_dlt__extracted_on",
    "_dlt__extracted_hour",
    "_dlt__file_name",
}
BUSINESS = {
    "product_number",
    "name",
    "color",
    "product_line",
    "sell_start_date",
    "sell_end_date",
    "discontinued_date",
    "modified_date",
}


SUBCATEGORY_LOAD = "1717001800.25"
SUBCATEGORY_ROWS = [
    subcategory(1, "Mountain Bikes", category=1),
    subcategory(4, "Bottom Brackets", category=2, modified="2008-04-30"),
]


@pytest.fixture(scope="module")
def staged(make_workspace):
    """One load of three products and one of two subcategories, built through raw and conform only."""
    ws = make_workspace("conform")
    rows = [
        product(1, "CF-0001", "Trailing space", line="R "),
        product(2, "CF-0002", "Blank line", line="  "),
        product(3, "CF-0003", "Null line", line=None),
    ]
    landed = ws.write_load(1, rows)
    write_load(ws.lake, SUBCATEGORY_LOAD, SUBCATEGORY_ROWS, resource=SUBCATEGORIES)
    require(ws.generate())
    snap = ws.snapshot("built", require(ws.build("--select", "+path:models/conform")))
    return snap, landed


def test_platform_columns(staged):
    """AC6: snake_case business columns and exactly the six _dlt__ platform columns."""
    snap, _ = staged
    columns = snap.columns("conform", snap.staged())
    assert {c for c in columns if c.startswith("_dlt__")} == PLATFORM
    assert BUSINESS <= set(columns), sorted(BUSINESS - set(columns))
    assert "_contract__cast_failed" in columns
    assert [c for c in columns if not SNAKE.match(c)] == []


def test_platform_values(staged):
    """AC6: _dlt__extracted_at is the load id as a timestamp; on, hour and file name come from the landed file."""
    snap, landed = staged
    load = load_id(1)
    when = datetime.fromtimestamp(float(load), UTC)
    rows = snap.sql(
        "select distinct _dlt__load_id, epoch_us(_dlt__extracted_at), cast(_dlt__extracted_on as varchar), "
        f"cast(_dlt__extracted_hour as integer), _dlt__file_name from conform.{q(snap.staged())}"
    )
    assert len(rows) == 1, rows
    load_col, extracted_at, extracted_on, hour, file_name = rows[0]
    assert load_col == load
    assert extracted_at == epoch_us(load)
    assert extracted_on == f"{when:%Y-%m-%d}"
    assert hour == when.hour
    assert file_name.endswith(landed.name)
    ids = snap.sql(f"select count(distinct _dlt__id), count(*) from conform.{q(snap.staged())}")
    assert ids == [(3, 3)]


def test_product_line_trimmed(staged):
    """AC7, EC5: 'R ' lands as 'R', blank as '', and null stays null."""
    snap, _ = staged
    lines = dict(snap.sql(f"select product_number, product_line from conform.{q(snap.staged())}"))
    assert lines == {"CF-0001": "R", "CF-0002": "", "CF-0003": None}


def test_contract_trims_product_line():
    """AC7 ([14]): the trim lives in the contract as transformLogic: trim(value)."""
    contract = yaml.safe_load((REPO / CONTRACT_PATH).read_text())
    logic = []

    def walk(node):
        if isinstance(node, dict):
            if "transformLogic" in node:
                logic.append(node)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(contract)
    assert any(
        str(n["transformLogic"]).replace(" ", "") == "trim(value)" and "line" in str(n).lower() for n in logic
    ), logic


def test_live_shape_is_read(staged):
    """F14: the feed's live names (ProductId, Rowguid, ...Id) and plain YYYY-MM-DD dates all stage populated."""
    snap, _ = staged
    rows = snap.sql(
        "select product_number, product_id, rowguid, product_subcategory_id, product_model_id, "
        "cast(sell_start_date as varchar), cast(cast(modified_date as date) as varchar) "
        f"from conform.{q(snap.staged())} order by product_number"
    )
    assert rows == [
        ("CF-0001", 1, "00000000-0000-0000-0000-000000000001", 14, 19, "2011-05-31", "2014-02-08"),
        ("CF-0002", 2, "00000000-0000-0000-0000-000000000002", 14, 19, "2011-05-31", "2014-02-08"),
        ("CF-0003", 3, "00000000-0000-0000-0000-000000000003", 14, 19, "2011-05-31", "2014-02-08"),
    ]
    failed = snap.sql(f"select count(*) from conform.{q(snap.staged())} where len(_contract__cast_failed) > 0")
    assert failed == [(0,)], "a plain-date value failed its cast"


def test_product_contract_lives_in_its_source_folder():
    """AC15 ([2]): the Product contract is contracts/adventure_works/products.yaml, the flat file is gone,
    its id is unchanged, and the models generated from it keep their names."""
    assert (REPO / CONTRACT_PATH).is_file()
    assert not (REPO / "contracts" / f"{CONTRACT}.yaml").exists()
    assert sorted(p.relative_to(REPO).as_posix() for p in (REPO / "contracts").glob("*.yaml")) == []
    assert yaml.safe_load((REPO / CONTRACT_PATH).read_text())["id"] == CONTRACT
    for generated in (
        f"models/raw/adventure_works/raw__{CONTRACT}.sql",
        f"models/conform/adventure_works/{CONTRACT}.sql",
        f"models/conform/adventure_works/{CONTRACT}.yml",
    ):
        assert (REPO / generated).is_file(), generated


def test_product_subcategories(staged):
    """Story #6 AC13 ([13]): contracts/adventure_works/product_subcategories.yaml declares
    adventure_works__product_subcategories, and conform stages its landed rows with snake_case columns,
    the six platform columns and the feed's values."""
    contract = yaml.safe_load((REPO / SUBCATEGORIES_CONTRACT_PATH).read_text())
    assert contract["id"] == SUBCATEGORIES, contract["id"]
    snap, _ = staged
    tables = {n for n, kind in snap.relations("conform").items() if kind == "BASE TABLE"}
    assert SUBCATEGORIES in tables, f"conform stages no {SUBCATEGORIES}: {sorted(tables)}"
    columns = snap.columns("conform", SUBCATEGORIES)
    assert {c for c in columns if c.startswith("_dlt__")} == PLATFORM
    assert {"product_subcategory_id", "product_category_id", "name", "rowguid", "modified_date"} <= set(columns), columns
    assert [c for c in columns if not SNAKE.match(c)] == []
    rows = snap.sql(
        "select product_subcategory_id, product_category_id, name, rowguid, "
        "cast(cast(modified_date as date) as varchar), _dlt__load_id, epoch_us(_dlt__extracted_at) "
        f"from conform.{q(SUBCATEGORIES)} order by 1"
    )
    assert rows == [
        (1, 1, "Mountain Bikes", SUBCATEGORY_ROWS[0]["Rowguid"], "2008-04-30", SUBCATEGORY_LOAD, epoch_us(SUBCATEGORY_LOAD)),
        (4, 2, "Bottom Brackets", SUBCATEGORY_ROWS[1]["Rowguid"], "2008-04-30", SUBCATEGORY_LOAD, epoch_us(SUBCATEGORY_LOAD)),
    ]
    assert snap.staged() == CONTRACT, "the Products staged table is not the one its contract names"
