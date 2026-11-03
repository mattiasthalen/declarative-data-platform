"""Story #6 in serve: the product_subcategory dimension and the split bridge__product (AC1 to AC3,
AC9, AC10, AC12, EC1, EC2, EC4, EC6, and AC11 on the story lake).

The story lake is ``tie_story``'s; every test reads the snapshots its builds left.
"""

from __future__ import annotations

import re
from collections import defaultdict

import pytest
import tie_story
import yaml
from harness import GHOSTS, REPO, Snapshot, dimension_column, pr_id, q
from tie_story import (
    D0,
    FIRST,
    LABELS,
    LAST,
    MOVE,
    RENAME,
    STAGED,
    pit_key_problems,
    split_bridge,
    subcategory_on,
    tiling_problems,
)

NOT_AVAILABLE = "[not available]"


@pytest.fixture(scope="module")
def story(make_workspace) -> tie_story.Story:
    return tie_story.run(make_workspace("split-bridge"))


def _rows_of(snap: Snapshot, number: str) -> list[tuple]:
    """(_key__product_subcategory, valid_from, valid_to) of one product's bridge__product rows."""
    identity = str(pr_id(snap, number))
    return [(ks, f, t) for i, _, ks, f, t in split_bridge(snap) if i == identity]


def _subcategory_identity(snap: Snapshot, source_id: int) -> str:
    rows = snap.sql(
        "select distinct split_part(_key__product_subcategory, '|', 1) from serve__uss.product_subcategory "
        "where cast(product_subcategory__source_id as varchar) = ?",
        [str(source_id)],
    )
    assert len(rows) == 1, f"product_subcategory holds {len(rows)} identities for source id {source_id}"
    return rows[0][0]


def _reads(snap: Snapshot, number: str, day: str):
    return subcategory_on(snap, pr_id(snap, number), day)


# --------------------------------------------------------------------------- AC1, EC2


def test_bridge_one_row_per_instant(story):
    """AC1, EC2 ([9]): after every build, for every product, bridge__product's [_valid_from, _valid_to)
    tile 0001-01-01 to 9999-12-31: no gap, no overlap. SN-0001's move and rename at one ChangedAt
    split it once."""
    for label in LABELS:
        snap = story.snap(label)
        problems = tiling_problems(snap)
        assert not problems, f"after {label}:\n" + "\n".join(problems[:20])
    for label in ("L3", "L4", "L5", "full"):
        snap = story.snap(label)
        rows = _rows_of(snap, "SN-0001")
        assert [(f, t) for _, f, t in rows] == [(FIRST, tie_story._moment(MOVE)), (tie_story._moment(MOVE), LAST)], (
            f"after {label}, SN-0001's rows: {rows}"
        )


# --------------------------------------------------------------------------- AC2


def test_bridge_pit_keys_cover(story):
    """AC2 ([9]): each bridge__product row's _key__product and _key__product_subcategory name the versions
    valid for the whole row interval: each dimension row's [valid_from, valid_to) contains it."""
    checked = 0
    for label in LABELS:
        snap = story.snap(label)
        problems = pit_key_problems(snap)
        assert not problems, f"after {label}:\n" + "\n".join(problems[:20])
        checked += snap.sql(
            f"select count(*) from {STAGED}.bridge__product where _key__product_subcategory not in "
            "('[not available]', '[not applicable]')"
        )[0][0]
    assert checked, "no bridge__product row carries a subcategory key: the check proves nothing"


# --------------------------------------------------------------------------- AC3, EC1


def test_bridge_dimension_change(story):
    """AC3, EC1 ([9] [11]): after L4, through _bridge and the dimensions, SN-0001 reads Mountain Bikes on
    2014-02-20 and Road Bikes on 2014-03-15; SN-0005 reads Mountain Bikes on 2014-03-20 and Mountain on
    2014-04-15. Renaming subcategory 4, which no product is tied to, splits no product row."""
    s3, s4 = story.snap("L3"), story.snap("L4")
    assert _reads(s4, "SN-0001", "2014-02-20") == "Mountain Bikes"
    assert _reads(s4, "SN-0001", "2014-03-15") == "Road Bikes"
    assert _reads(s4, "SN-0005", "2014-03-20") == "Mountain Bikes"
    assert _reads(s4, "SN-0005", "2014-04-15") == "Mountain"
    assert _reads(s4, "SN-0005", "2014-03-31 23:59:59") == "Mountain Bikes"
    assert _reads(s4, "SN-0005", RENAME) == "Mountain"
    assert _reads(s3, "SN-0005", "2014-04-15") == "Mountain Bikes"

    # EC1: subcategory 4's rename is a version of its own, and no product row splits on it.
    four = _subcategory_identity(s4, 4)
    versions = s4.sql(
        "select product_subcategory__name from serve__uss.product_subcategory "
        "where split_part(_key__product_subcategory, '|', 1) = ? order by product_subcategory__valid_from",
        [four],
    )
    assert versions == [("Bottom Brackets",), ("Brackets",)], versions
    for label in LABELS:
        snap = story.snap(label)
        tied = [r for r in split_bridge(snap) if r[2] is not None and r[2].split("|")[0] == four]
        assert not tied, f"after {label}, product rows name subcategory 4: {tied}"
    five = str(pr_id(s4, "SN-0005"))
    before = [r for r in split_bridge(s3) if r[0] != five]
    after = [r for r in split_bridge(s4) if r[0] != five]
    assert after == before, "L4's renames changed the bridge rows of a product not tied to subcategory 1 then"
    assert [(f, t) for _, f, t in _rows_of(s4, "SN-0005")] == [
        (FIRST, tie_story._moment(RENAME)),
        (tie_story._moment(RENAME), LAST),
    ]


# --------------------------------------------------------------------------- AC9


def test_bridge_backfill(story):
    """AC9 ([9] [10]): serve backfills the tie's first version: on 2010-01-01 SN-0001 reads Mountain Bikes
    through the bridge, and SN-0002, never in a subcategory, reads [not available]."""
    for label in ("L1", "L2", "L3", "L4", "L5", "full"):
        snap = story.snap(label)
        assert _reads(snap, "SN-0001", "2010-01-01") == "Mountain Bikes", label
        assert _reads(snap, "SN-0001", D0) == "Mountain Bikes", label
        for day in ("2010-01-01", "2014-02-20", "2014-06-01"):
            assert _reads(snap, "SN-0002", day) == NOT_AVAILABLE, f"{label}, SN-0002 on {day}"
    assert _reads(story.snap("L1"), "SN-0004", "2010-01-01") == NOT_AVAILABLE
    assert _reads(story.snap("L2"), "SN-0004", "2010-01-01") == "Touring Bikes"


# --------------------------------------------------------------------------- EC4


def test_tie_retraction_gap_through_bridge(story):
    """EC4 ([4] [9]): SN-0003 reads [not available] only while its tie is retracted: in the builds after
    L3 and L4, at every instant; before L3 and after L5 restores it, at none."""
    days = ("2010-01-01", "2014-02-20", "2014-03-15", "2014-05-15", "2020-01-01")
    for label in ("L3", "L4"):
        snap = story.snap(label)
        for day in days:
            assert _reads(snap, "SN-0003", day) == NOT_AVAILABLE, f"after {label}, SN-0003 on {day}"
    for label in ("L2", "L5", "full"):
        snap = story.snap(label)
        for day in days:
            assert _reads(snap, "SN-0003", day) == "Road Bikes", f"after {label}, SN-0003 on {day}"


# --------------------------------------------------------------------------- AC10


def _serve_on_sale(snap: Snapshot, day: str) -> dict[str, int]:
    start, end, gone = (dimension_column(snap, w) for w in ("sell_start", "sell_end", "discontinued"))
    d = f"date '{day}'"
    rows = snap.sql(
        "select ps.product_subcategory__name, count(*) from serve__uss._bridge b "
        "join serve__uss.product p on p._key__product = b._key__product "
        "left join serve__uss.product_subcategory ps on ps._key__product_subcategory = b._key__product_subcategory "
        f"where b.stage = 'product' and b._valid_from <= {d} and {d} < b._valid_to "
        f"and cast(p.{q(start)} as date) <= {d} "
        f"and (p.{q(end)} is null or cast(p.{q(end)} as date) >= {d}) "
        f"and (p.{q(gone)} is null or {d} < cast(p.{q(gone)} as date)) "
        "group by all"
    )
    return {name: count for name, count in rows}


def test_on_sale_per_subcategory(story):
    """AC10 ([9]): products on sale per subcategory name, from _bridge and the two dimensions, equal the
    count computed from the story lake's rows: on 2014-03-15 after L4, and on later days after L5."""
    expected = tie_story.on_sale_per_subcategory("2014-03-15", 4)
    assert expected == {"Road Bikes": 2, "Touring Bikes": 1, "Mountain Bikes": 1, NOT_AVAILABLE: 1}, (
        f"the replay of the story lake disagrees with the spec's own reading: {expected}"
    )
    assert _serve_on_sale(story.snap("L4"), "2014-03-15") == expected
    for day in ("2014-03-15", "2014-04-15", "2014-05-15"):
        assert _serve_on_sale(story.snap("L5"), day) == tie_story.on_sale_per_subcategory(day, 5), day


# --------------------------------------------------------------------------- AC12


def _bridge_key_tests(snap: Snapshot) -> dict[str, dict[str, dict]]:
    """column -> test name -> manifest node, of every data test on serve__uss._bridge."""
    found: dict[str, dict[str, dict]] = defaultdict(dict)
    for node in snap.manifest["nodes"].values():
        if node.get("resource_type") != "test":
            continue
        attached = node.get("attached_node") or ""
        if not attached.endswith("._bridge"):
            continue
        name = (node.get("test_metadata") or {}).get("name")
        found[node.get("column_name")][name] = node
    return found


def test_bridge_key_tests(story):
    """AC12 ([8] [12]): _bridge has _key__product_subcategory; on product_subcategory stage rows _key__product
    is [not applicable]; the relationship and not_null tests on the inherited key run at severity warn,
    while _key__product's stay at error."""
    snap = story.snap("L5")
    assert "_key__product_subcategory" in snap.columns("serve__uss", "_bridge"), snap.columns("serve__uss", "_bridge")
    assert "bridge__product_subcategory" in snap.relations(STAGED), sorted(snap.relations(STAGED))

    stage_rows = snap.sql(
        "select _key__product, _key__product_subcategory from serve__uss._bridge where stage = 'product_subcategory'"
    )
    assert stage_rows, "_bridge holds no product_subcategory stage row"
    assert {k for k, _ in stage_rows} == {"[not applicable]"}, stage_rows
    versions = {r[0] for r in snap.sql("select _key__product_subcategory from serve__uss.product_subcategory")}
    assert {k for _, k in stage_rows} <= versions - set(GHOSTS), stage_rows
    assert len(stage_rows) == len(versions - set(GHOSTS)), "not one product_subcategory stage row per version"

    tests = _bridge_key_tests(snap)
    inherited = tests.get("_key__product_subcategory", {})
    for name in ("not_null", "relationships"):
        assert name in inherited, f"_bridge._key__product_subcategory has no {name} test: {sorted(inherited)}"
        severity = str(inherited[name]["config"].get("severity", "")).lower()
        assert severity == "warn", f"_bridge._key__product_subcategory {name} runs at {severity!r}"
    to = str(inherited["relationships"]["test_metadata"].get("kwargs", {}).get("to", ""))
    assert "product_subcategory" in to, f"the relationship test points to {to!r}"
    own = tests.get("_key__product", {})
    for name in ("not_null", "relationships"):
        assert name in own, f"_bridge._key__product has no {name} test: {sorted(own)}"
        severity = str(own[name]["config"].get("severity", "")).lower()
        assert severity == "error", f"_bridge._key__product {name} runs at {severity!r}"


# --------------------------------------------------------------------------- AC11, EC6

SERVED = (
    ("serve__uss", "product"),
    ("serve__uss", "product_subcategory"),
    ("serve__uss", "_bridge"),
    (STAGED, "bridge__product"),
)


def test_incremental_equals_full_on_story_lake(story):
    """AC11, EC6 ([11]): the builds after L4 (subcategories only) and L5, incremental, leave product,
    product_subcategory, _bridge and bridge__product row-identical to a --full-refresh. L4's build rebuilds
    the bridge rows of the products tied to the renamed subcategories, and only theirs."""
    incremental, full = story.snap("L5"), story.snap("full")
    for schema, table in SERVED:
        query = f"select * from {schema}.{q(table)} order by all"
        assert incremental.sql(query) == full.sql(query), f"{schema}.{table} differs from a full refresh"

    s3, s4 = story.snap("L3"), story.snap("L4")
    query = "select * from serve__uss.product order by all"
    assert s4.sql(query) == s3.sql(query), "a subcategories-only build changed the product dimension"
    tied = {str(pr_id(s4, "SN-0005"))}
    changed = {r[0] for r in set(split_bridge(s3)) ^ set(split_bridge(s4))}
    assert changed == tied, f"the subcategories-only build changed the bridge rows of {changed}, expected {tied}"


# --------------------------------------------------------------------------- review ledger #1, #2
# These read the committed generated output; test_generate_check holds it to what the generator writes.

SERVE = REPO / "models" / "serve"
CONFIG = re.compile(r"\{\{\s*config\((.*?)\)\s*\}\}", re.S)


def test_tied_dimension_keeps_its_uss_entry():
    """Ledger #1: product, whose staged bridge follows a tie, keeps its own entry in uss.yml: not_null,
    unique and ghost_rows on _key__product, and a description for each of its attribute columns."""
    models = {m["name"]: m for m in yaml.safe_load((SERVE / "uss" / "uss.yml").read_text())["models"]}
    assert "product" in models, f"uss.yml has no entry for product: {sorted(models)}"
    columns = {c["name"]: c for c in models["product"].get("columns") or []}
    key = columns.get("_key__product")
    assert key is not None, f"uss.yml's product entry has no _key__product: {sorted(columns)}"
    tests = {t if isinstance(t, str) else next(iter(t)) for t in key.get("data_tests") or []}
    assert {"not_null", "unique", "ghost_rows"} <= tests, f"_key__product carries only {sorted(tests)}"

    selected = set(re.findall(r"\bas (product__\w+)", (SERVE / "uss" / "product.sql").read_text()))
    attributes = selected - {"product__valid_from", "product__valid_to"}
    assert len(attributes) >= 7, f"product.sql selects too few attribute columns: {sorted(selected)}"
    undescribed = sorted(c for c in attributes if not str((columns.get(c) or {}).get("description") or "").strip())
    assert undescribed == [], f"uss.yml's product entry describes none of {undescribed}"


def test_serve_incremental_models_fail_on_schema_change():
    """Ledger #2: every incremental serve model, staged bridges and dimensions, is configured with
    on_schema_change='fail', so a column change fails the build instead of being ignored."""
    incremental = {}
    for path in sorted(SERVE.rglob("*.sql")):
        match = CONFIG.search(path.read_text())
        if match and re.search(r"materialized\s*=\s*['\"]incremental['\"]", match.group(1)):
            incremental[path.stem] = match.group(1)
    expected = {"product", "product_subcategory", "bridge__product", "bridge__product_subcategory"}
    assert expected <= set(incremental), f"incremental serve models: {sorted(incremental)}"
    lax = sorted(
        name for name, args in incremental.items()
        if not re.search(r"on_schema_change\s*=\s*['\"]fail['\"]", args)
    )
    assert lax == [], f"incremental serve models without on_schema_change='fail': {lax}"
