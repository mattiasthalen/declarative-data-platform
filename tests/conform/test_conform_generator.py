"""Conform: the staged Products model built by dbt from the generated raw and conform models (AC6, AC7, EC5)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
import yaml

from harness import CONTRACT, REPO, SNAKE, epoch_us, load_id, product, q, require

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


@pytest.fixture(scope="module")
def staged(make_workspace):
    """One load of three products, built through raw and conform only."""
    ws = make_workspace("conform")
    rows = [
        product(1, "CF-0001", "Trailing space", line="R "),
        product(2, "CF-0002", "Blank line", line="  "),
        product(3, "CF-0003", "Null line", line=None),
    ]
    landed = ws.write_load(1, rows)
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
    contract = yaml.safe_load((REPO / "contracts" / f"{CONTRACT}.yaml").read_text())
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
