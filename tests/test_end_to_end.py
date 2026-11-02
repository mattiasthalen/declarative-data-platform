"""End to end: a synthetic lake through `task generate` and `dbt build` into DuckDB (S1).

Each scenario runs in its own copy of the repo with its own lake and warehouse, and keeps a
snapshot of the warehouse after every build. The main story:

    s1  load 1 (eight products)                                   build
    s2  no new files                                              build
    s3  load 2, identical to load 1                               build
    s4  load 3: colour change, name correction, sell end nulled,
        "n/a" sell start, one product missing, one product new    build
    s5  loads 4 and 5 together: a colour B then back to A         build
    s6  a description in anchor/model.yaml changes      generate, build
    s7  no new files                                    build --full-refresh

The point-in-time perspective pPR_Product is read from the same snapshots (story #4), and so
is the time-traveling perspective tPR_Product (story #5).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

import pytest
import yaml

from harness import (
    ATTRIBUTES,
    CONTRACT,
    GHOSTS,
    PIT,
    SCHEMAS,
    TT,
    Snapshot,
    Workspace,
    annex,
    annexes,
    at,
    attribute,
    dimension_column,
    epoch_us,
    ghost_rows,
    integrity_violations,
    latest,
    load_id,
    pit,
    pit_columns,
    posit,
    posited,
    posits,
    pr_id,
    product,
    q,
    require,
    tail,
    tt,
    tt_columns,
)

M0, M1, M2 = "2014-02-08", "2014-03-01", "2014-04-01"
D0, D1, D2 = "2014-02-08", "2014-03-01", "2014-04-01"
L1, L2, L3, L4, L5 = (load_id(n) for n in range(1, 6))


def base_products() -> dict[str, dict]:
    return {
        "SC-0001": product(1, "SC-0001", "Colour Bike", color="Black", line="R "),
        "SN-0002": product(2, "SN-0002", "Alpha"),
        "SE-0003": product(3, "SE-0003", "Ending Bike", sell_end="2013-05-29"),
        "SG-0004": product(4, "SG-0004", "Gone Bike"),
        "SX-0005": product(5, "SX-0005", "Cast Bike"),
        "SA-0006": product(6, "SA-0006", "ABA One Build", color="Blue"),
        "SB-0007": product(7, "SB-0007", "ABA Three Builds", color="Blue"),
        "SS-0008": product(8, "SS-0008", "Steady Bike", discontinued="2015-01-01"),
    }


def load_3() -> dict[str, dict]:
    rows = base_products()
    del rows["SG-0004"]  # EC3: missing from a full load
    rows["SC-0001"].update(Color="Red", ModifiedDate=M1)  # AC10: new value, later ChangedAt
    rows["SN-0002"].update(Name="Alpha Prime")  # AC11: other value at a held ChangedAt
    rows["SE-0003"].update(SellEndDate=None)  # AC12: source null retracts
    rows["SX-0005"].update(SellStartDate="n/a")  # AC19: failed cast
    rows["SB-0007"].update(Color="Yellow", ModifiedDate=M1)  # EC4: B
    rows["SN-0009"] = product(9, "SN-0009", "Newcomer")  # AC13: new product number
    return rows


def load_4() -> dict[str, dict]:
    rows = load_3()
    rows["SA-0006"].update(Color="Yellow", ModifiedDate=M1)  # EC2: B in the older load
    rows["SB-0007"].update(Color="Blue", ModifiedDate=M2)  # EC4: back to A
    return rows


def load_5() -> dict[str, dict]:
    rows = load_4()
    rows["SA-0006"].update(Color="Blue", ModifiedDate=M2)  # EC2: back to A in the newer load
    return rows


# The error the crt load raises on a contradiction (macros/integrate/anchor.sql, ADR-0006).
CONTRADICTION = "two different values for one version at one PositedAt"


class Story:
    """Runs the steps in order and stops at the first that fails; keeps a snapshot per good build."""

    def __init__(self, ws: Workspace):
        self.ws = ws
        self.snaps: dict[str, Snapshot] = {}
        self.failure = "it has not run"

    def ok(self, step, what: str) -> bool:
        if step.returncode != 0:
            self.failure = f"{what} exited {step.returncode}:\n{tail(step.output)}"
        return step.returncode == 0

    def build(self, label: str, *args: str) -> bool:
        step = self.ws.build(*args)
        if not self.ok(step, f"dbt build for {label}"):
            return False
        self.snaps[label] = self.ws.snapshot(label, step)
        return True

    def generate(self) -> bool:
        return self.ok(self.ws.generate(), "task generate")

    def snap(self, label: str) -> Snapshot:
        if label not in self.snaps:
            pytest.fail(f"the story never reached {label}: {self.failure}")
        return self.snaps[label]


@pytest.fixture(scope="module")
def story(make_workspace) -> Story:
    ws = make_workspace("story")
    s = Story(ws)
    ws.write_load(1, list(base_products().values()))
    if not (s.generate() and s.build("s1") and s.build("s2")):
        return s
    ws.write_load(2, list(base_products().values()))
    if not s.build("s3"):
        return s
    ws.write_load(3, list(load_3().values()))
    if not s.build("s4"):
        return s
    ws.write_load(4, list(load_4().values()))
    ws.write_load(5, list(load_5().values()))
    if not s.build("s5"):
        return s
    model = ws.root / "anchor" / "model.yaml"
    document = yaml.safe_load(model.read_text())
    assert _revise_first_description(document), "anchor/model.yaml has no description to revise"
    model.write_text(yaml.safe_dump(document, sort_keys=False, allow_unicode=True))
    if s.generate() and s.build("s6"):
        s.build("s7", "--full-refresh")
    return s


def _revise_first_description(node) -> bool:
    if isinstance(node, dict):
        for key, value in node.items():
            if key.lstrip("@") == "description" and isinstance(value, str):
                node[key] = value + " Revised."
                return True
            if _revise_first_description(value):
                return True
    elif isinstance(node, list):
        return any(_revise_first_description(item) for item in node)
    return False


def _tests(snap: Snapshot) -> list[dict]:
    return [r for r in snap.results() if r["unique_id"].startswith("test.")]


def _batches(snap: Snapshot) -> list[tuple]:
    return snap.load_log()


# --------------------------------------------------------------------------- AC1, AC18, AC8


def test_build_from_empty(story):
    """AC1: uv sync, task generate and dbt build --target dev exit 0 from an empty database over one load."""
    snap = story.snap("s1")
    assert snap.count("conform", snap.staged()) == 8


def test_schema_names(story):
    """AC18: the schemas are exactly raw, conform, integrate, serve__uss_staging, serve__uss."""
    snap = story.snap("s1")
    used = {
        r[0]
        for r in snap.sql(
            "select distinct table_schema from information_schema.tables "
            "where table_schema not in ('information_schema', 'pg_catalog')"
        )
    }
    assert used == set(SCHEMAS), f"schemas holding relations: {sorted(used)}"


def test_anchor_objects(story):
    """AC8: integrate holds the anchor, per attribute posit/annex/view, lPR_Product, key and pkey, with Roenbaeck's columns."""
    snap = story.snap("s1")
    names = set(snap.relations("integrate"))
    expected = {"PR_Product", "lPR_Product", "key_PR_Product_NUM", "pkey_PR_Product_NUM"}
    for m in ATTRIBUTES:
        expected |= {attribute(m), posit(m), annex(m)}
    assert expected <= names, f"missing from integrate: {sorted(expected - names)}"

    assert {"PR_ID", "Metadata_PR"} <= set(snap.columns("integrate", "PR_Product"))
    for m in ATTRIBUTES:
        assert {f"PR_{m}_ID", f"PR_{m}_PR_ID", attribute(m), f"PR_{m}_ChangedAt"} <= set(
            snap.columns("integrate", posit(m))
        ), posit(m)
        assert {
            f"PR_{m}_ID",
            f"PR_{m}_PositedAt",
            f"PR_{m}_Positor",
            f"PR_{m}_Reliability",
            f"Metadata_PR_{m}",
        } <= set(snap.columns("integrate", annex(m))), annex(m)
        assert {"PR_ID", attribute(m)} <= set(snap.columns("integrate", "lPR_Product"))


# --------------------------------------------------------------------------- AC2, AC3


def test_second_build_appends_nothing(story):
    """AC2: a second build with no new lake files adds no row to conform, integrate or either serve schema."""
    before = story.snap("s1").counts(SCHEMAS[1:])
    after = story.snap("s2").counts(SCHEMAS[1:])
    assert after == before


def test_identical_load_posits_nothing(story):
    """AC3: an identical second load grows the staged model by the load; every posit and annex stays the same size."""
    s2, s3 = story.snap("s2"), story.snap("s3")
    staged = s2.staged()
    assert s3.count("conform", staged) == s2.count("conform", staged) + 8
    for m in ATTRIBUTES:
        for table in (posit(m), annex(m)):
            assert s3.count("integrate", table) == s2.count("integrate", table), table
    assert s3.count("integrate", "PR_Product") == s2.count("integrate", "PR_Product")


# --------------------------------------------------------------------------- AC9 .. AC13


def test_three_timelines(story):
    """AC9: load 1's annex rows carry PositedAt = its _dlt__extracted_at, Positor 0, Reliability 1, Metadata = the batch; posits carry ChangedAt = modified_date."""
    snap = story.snap("s1")
    batches = _batches(snap)
    assert len(batches) == 1, batches
    batch = batches[0][0]
    staged = snap.staged()
    extracted = snap.sql(f"select distinct epoch_us(_dlt__extracted_at) from conform.{q(staged)}")
    assert extracted == [(epoch_us(L1),)]
    total = 0
    for m in ATTRIBUTES:
        rows = snap.sql(
            f"select epoch_us(PR_{m}_PositedAt), PR_{m}_Positor, PR_{m}_Reliability, Metadata_PR_{m} "
            f"from integrate.{q(annex(m))}"
        )
        total += len(rows)
        for row in rows:
            assert row == (epoch_us(L1), 0, 1, batch), f"{annex(m)}: {row}"
        changed = snap.sql(
            f"select distinct cast(cast(PR_{m}_ChangedAt as date) as varchar) from integrate.{q(posit(m))}"
        )
        assert changed in ([], [(D0,)]), f"{posit(m)} ChangedAt {changed}"
    # 8 products x (NUM, NAM, LIN, COL, SST) + one SEN + one DIS
    assert total == 8 * 5 + 2


def test_new_value_is_new_version(story):
    """AC10: a colour change at a later modified_date adds one posit and one annex for PR_COL only."""
    s3, s4 = story.snap("s3"), story.snap("s4")
    pid = pr_id(s4, "SC-0001")
    before, after = set(posits(s3, "COL", pid)), set(posits(s4, "COL", pid))
    assert before < after
    assert [(v, d) for _, v, d in after - before] == [("Red", D1)]
    new = [r for r in annexes(s4, "COL", pid) if r not in annexes(s3, "COL", pid)]
    assert [(r[1], r[2], r[3]) for r in new] == [(epoch_us(L3), 0, 1)]
    for m in ATTRIBUTES:
        if m != "COL":
            assert posits(s4, m, pid) == posits(s3, m, pid), m
            assert annexes(s4, m, pid) == annexes(s3, m, pid), m
    assert latest(s4, "SC-0001", "COL") == "Red"


def test_correction_retracts(story):
    """AC11: a name change at the same modified_date retracts the held posit (reliability 0) and asserts the new one at the new PositedAt."""
    s3, s4 = story.snap("s3"), story.snap("s4")
    pid = pr_id(s4, "SN-0002")
    old = posits(s3, "NAM", pid)
    assert [(v, d) for _, v, d in old] == [("Alpha", D0)]
    now = {v: (i, d) for i, v, d in posits(s4, "NAM", pid)}
    assert {v: d for v, (_, d) in now.items()} == {"Alpha": D0, "Alpha Prime": D0}
    old_id, new_id = now["Alpha"][0], now["Alpha Prime"][0]
    new = sorted(r for r in annexes(s4, "NAM", pid) if r not in annexes(s3, "NAM", pid))
    assert sorted([(old_id, epoch_us(L3), 0, 0), (new_id, epoch_us(L3), 0, 1)]) == new
    assert latest(s4, "SN-0002", "NAM") == "Alpha Prime"


def test_source_null_retracts(story):
    """AC12: a sell end that became null in the source retracts the held sell end; a second null adds nothing."""
    s3, s4, s5 = story.snap("s3"), story.snap("s4"), story.snap("s5")
    pid = pr_id(s4, "SE-0003")
    assert posits(s4, "SEN", pid) == posits(s3, "SEN", pid)
    (held,) = posits(s4, "SEN", pid)
    new = [r for r in annexes(s4, "SEN", pid) if r not in annexes(s3, "SEN", pid)]
    assert new == [(held[0], epoch_us(L3), 0, 0)]
    assert latest(s4, "SE-0003", "SEN") is None
    assert annexes(s5, "SEN", pid) == annexes(s4, "SEN", pid)
    assert latest(s5, "SE-0003", "SEN") is None


def test_identity_by_key(story):
    """AC13: a product number seen in two loads keeps its PR_ID; a new number gets a new one."""
    s1, s3, s4 = story.snap("s1"), story.snap("s3"), story.snap("s4")
    first = {n: pr_id(s1, n) for n in base_products()}
    assert len(set(first.values())) == 8
    assert {n: pr_id(s4, n) for n in base_products()} == first
    assert pr_id(s4, "SN-0009") not in set(first.values())
    assert s3.count("integrate", "PR_Product") == 8
    assert s4.count("integrate", "PR_Product") == 9


# --------------------------------------------------------------------------- AC14, AC15


def test_load_log(story):
    """AC14: each build that writes Anchor rows adds one SUCCEEDED batch; Metadata values point at batches; an empty build adds none."""
    s1, s2, s3, s4, s5 = (story.snap(f"s{n}") for n in range(1, 6))
    assert [status for _, status in _batches(s1)] == ["SUCCEEDED"]
    assert _batches(s2) == _batches(s1)
    added_4 = [b for b in _batches(s4) if b not in _batches(s3)]
    assert [status for _, status in added_4] == ["SUCCEEDED"]
    added_5 = [b for b in _batches(s5) if b not in _batches(s4)]
    assert [status for _, status in added_5] == ["SUCCEEDED"]
    ids = [b for b, _ in _batches(s5)]
    assert len(ids) == len(set(ids))
    succeeded = {b for b, status in _batches(s5) if status == "SUCCEEDED"}
    assert s5.metadata_values() <= succeeded
    assert {added_4[0][0], added_5[0][0]} <= s5.metadata_values()


def test_schema_tracking(story):
    """AC15: _Schema keeps one row over unchanged builds and gains one when a description changes; _Anchor and _Attribute list PR and its seven attributes with descriptions."""
    for label in ("s1", "s2", "s3", "s4", "s5"):
        assert story.snap(label).count("integrate", "_Schema") == 1, label
    s6 = story.snap("s6")
    assert s6.count("integrate", "_Schema") == 2
    for label in ("s1", "s6"):
        snap = story.snap(label)
        anchors = _latest_rows(snap, "_Anchor")
        assert len(anchors) == 1 and "PR" in anchors[0].values(), anchors
        assert _description(anchors[0])
        attributes = _latest_rows(snap, "_Attribute")
        assert len(attributes) == 7, attributes
        for m in ATTRIBUTES:
            assert any(m in r.values() or f"PR_{m}" in r.values() for r in attributes), m
        assert all(_description(r) for r in attributes)


def _latest_rows(snap: Snapshot, view: str) -> list[dict]:
    cols = snap.columns("integrate", view)
    rows = [dict(zip(cols, r)) for r in snap.sql(f"select * from integrate.{q(view)}")]
    version = next((c for c in cols if c.lower() == "version"), None)
    if version is None:
        return rows
    newest = max(r[version] for r in rows)
    return [r for r in rows if r[version] == newest]


def _description(row: dict) -> str:
    value = next(v for k, v in row.items() if k.lower() == "description")
    return (value or "").strip()


# --------------------------------------------------------------------------- F1


def _anchor_rows(snap: Snapshot) -> dict[str, list[tuple]]:
    """Every row of the anchor, each posit and each annex, in a stable order."""
    tables = ["PR_Product"] + [t for m in ATTRIBUTES for t in (posit(m), annex(m))]
    return {t: snap.sql(f"select * from integrate.{q(t)} order by all") for t in tables}


def test_full_refresh_keeps_integrate(story):
    """F1, story #4 EC5, story #5 EC5: dbt build --full-refresh does not rebuild integrate: every anchor,
    posit and annex row stays as it was, and pPR_Product and tPR_Product, recreated by it, return the
    rows they returned before."""
    s6, s7 = story.snap("s6"), story.snap("s7")
    before, after = _anchor_rows(s6), _anchor_rows(s7)
    assert all(before.values()), "the story left an empty integrate table to compare"
    for table in before:
        assert after[table] == before[table], table
    for when in (at("2000-01-01"), at(D0), at(D1), at("2014-03-15"), at("2099-01-01")):
        query = f"select * from {PIT}({when}) order by all"
        rows = s6.sql(query)
        assert rows, f"pPR({when}) is empty before the full refresh"
        assert s7.sql(query) == rows, f"pPR({when}) changed over the full refresh"
    # Story #5 EC5: tPR is recreated too, and PositedAt comes from the lake, so as known at any K
    # the rows are the ones it returned before.
    for changing, positing in (
        (at("2000-01-01"), posited(L1)),
        (at(D0), posited(L3, -1)),
        (at(D0), posited(L3)),
        (at(D2), posited(L5, -1)),
        (at(D2), posited(L5)),
        (at("2099-01-01"), "date '9999-12-31'"),
    ):
        query = f"select * from {TT}({changing}, {positing}) order by all"
        rows = s6.sql(query)
        assert rows, f"tPR({changing}, {positing}) is empty before the full refresh"
        assert s7.sql(query) == rows, f"tPR({changing}, {positing}) changed over the full refresh"


# --------------------------------------------------------------------------- AC16, AC17, AC23


def _dimension_versions(snap: Snapshot) -> tuple[list[str], dict[str, list[tuple]]]:
    """Per identity, its versions in order: (valid_from, valid_to, from date, to date, *attribute values as text)."""
    attrs = [
        c
        for c in snap.columns("serve__uss", "product")
        if c.startswith("product__")
        and c not in ("product__valid_from", "product__valid_to")
        and "number" not in c
    ]
    rows = snap.sql(
        "select split_part(_key__product, '|', 1), cast(product__valid_from as varchar), "
        "cast(product__valid_to as varchar), cast(cast(product__valid_from as date) as varchar), "
        "cast(cast(product__valid_to as date) as varchar), "
        + ", ".join(f"cast({q(c)} as varchar)" for c in attrs)
        + " from serve__uss.product where _key__product like '%|%' order by 1, 4"
    )
    versions: dict[str, list[tuple]] = {}
    for row in rows:
        versions.setdefault(row[0], []).append(row[1:])
    return attrs, versions


def test_dimension_versions(story):
    """AC16: per product a first version from 0001-01-01 holding each attribute's earliest value, then one
    version per change; no version is all null; no gap and no overlap."""
    snap = story.snap("s5")
    attrs, versions = _dimension_versions(snap)
    color = attrs.index(dimension_column(snap, "color")) + 4
    assert len(versions) == 9
    for identity, vs in versions.items():
        assert vs[0][2] == "0001-01-01", (identity, vs[0])
        for v in vs:
            assert any(x is not None for x in v[4:]), f"a version of {identity} is all null: {v}"
        for earlier, later in zip(vs, vs[1:]):
            assert earlier[1] == later[0], f"gap or overlap in {identity}: {earlier} then {later}"
            assert earlier[4:] != later[4:], f"{identity} has a version that changes nothing: {earlier} then {later}"
        assert vs[-1][3] == "9999-12-31", (identity, vs[-1])
        earliest_color = posits(snap, "COL", int(identity))
        if earliest_color:
            first = min(earliest_color, key=lambda p: p[2])
            assert vs[0][color] == first[1], f"{identity}'s first version does not hold its earliest colour"
    by_number = {n: str(pr_id(snap, n)) for n in ("SA-0006", "SB-0007", "SC-0001", "SN-0002", "SS-0008")}
    for number in ("SA-0006", "SB-0007"):
        aba = versions[by_number[number]]
        assert [(v[2], v[color]) for v in aba] == [("0001-01-01", "Blue"), (D1, "Yellow"), (D2, "Blue")], number
    assert [(v[2], v[color]) for v in versions[by_number["SC-0001"]]] == [("0001-01-01", "Black"), (D1, "Red")]
    assert [v[2] for v in versions[by_number["SN-0002"]]] == ["0001-01-01"]
    assert [v[2] for v in versions[by_number["SS-0008"]]] == ["0001-01-01"]


def test_dbt_tests_pass_every_build(story):
    """AC17, AC23: every build ran the serve__uss and integrate data tests and none failed; IntegrityViolations is empty."""
    for label in ("s1", "s2", "s3", "s4", "s5", "s6"):
        snap = story.snap(label)
        bad = [(r["unique_id"], r["status"]) for r in _tests(snap) if r["status"] not in ("pass", "warn")]
        assert not bad, f"{label}: {bad}"
        assert integrity_violations(snap) == 0, label
    s1 = story.snap("s1")
    nodes = s1.manifest["nodes"]
    schema_of = {uid: n.get("schema") for uid, n in nodes.items()}

    def ran_on(schema: str) -> list[dict]:
        return [
            r
            for r in _tests(s1)
            if any(schema_of.get(d) == schema for d in nodes[r["unique_id"]]["depends_on"]["nodes"])
        ]

    assert ran_on("serve__uss"), "no dbt test ran against serve__uss"
    assert all(r["status"] == "pass" for r in ran_on("serve__uss"))
    assert ran_on("integrate"), "no dbt test ran against integrate"
    integrity = [
        r
        for r in _tests(s1)
        if "integrity" in r["unique_id"].lower()
        or any("integrity" in d.lower() for d in nodes[r["unique_id"]]["depends_on"]["nodes"])
    ]
    assert integrity and all(r["status"] == "pass" for r in integrity), "no passing IntegrityViolations test"


def test_ghost_rows_and_bridge(story):
    """AC17: exactly two ghost rows, and every _key__product in _bridge exists in the dimension."""
    snap = story.snap("s5")
    assert ghost_rows(snap) == {g: 1 for g in GHOSTS}
    assert {"stage", "_key__product", "_valid_from", "_valid_to"} <= set(
        snap.columns("serve__uss", "_bridge")
    )
    orphans = snap.sql(
        "select count(*) from serve__uss._bridge b "
        "where not exists (select 1 from serve__uss.product p where p._key__product = b._key__product)"
    )
    assert orphans == [(0,)]
    assert snap.count("serve__uss", "_bridge") > 0


# --------------------------------------------------------------------------- AC19, EC2, EC3, EC4


def test_cast_failure_does_not_retract(story):
    """AC19: "n/a" sell start stages as null with _contract__cast_failed, warns naming property and contract, and retracts nothing."""
    s1, s3, s4 = story.snap("s1"), story.snap("s3"), story.snap("s4")
    staged = s4.staged()
    rows = s4.sql(
        f"select sell_start_date, _contract__cast_failed from conform.{q(staged)} "
        "where product_number = ? and _dlt__load_id = ?",
        ["SX-0005", L3],
    )
    assert rows == [(None, ["sell_start_date"])]
    clean = s4.sql(
        f"select count(*) from conform.{q(staged)} where _dlt__load_id = ? and len(_contract__cast_failed) > 0",
        [L1],
    )
    assert clean == [(0,)]
    pid = pr_id(s4, "SX-0005")
    assert annexes(s4, "SST", pid) == annexes(s3, "SST", pid)
    assert all(r[3] == 1 for r in annexes(s4, "SST", pid))
    assert latest(s4, "SX-0005", "SST")[:10] == "2011-05-31"
    assert _warns_about(s4, "sell_start_date"), (
        f"no warn naming sell_start_date and {CONTRACT}:\n{tail(s4.output)}"
    )
    assert not _warns_about(s1, "sell_start_date")


def _warns_about(snap: Snapshot, prop: str) -> bool:
    def names(text: str) -> bool:
        return prop in text and CONTRACT in text

    if any(
        r["status"] == "warn" and names(r["unique_id"] + " " + str(r.get("message"))) for r in _tests(snap)
    ):
        return True
    return any(re.search(r"\bWARN\b", line) and names(line) for line in snap.output.splitlines())


def test_two_loads_one_build(story):
    """EC2: two loads between builds are both staged and applied oldest first: A, B, A is three versions."""
    s4, s5 = story.snap("s4"), story.snap("s5")
    staged = s5.staged()
    assert s5.count("conform", staged) == s4.count("conform", staged) + 2 * 8
    pid = pr_id(s5, "SA-0006")
    assert [(v, d) for _, v, d in posits(s5, "COL", pid)] == [("Blue", D0), ("Yellow", D1), ("Blue", D2)]
    assert latest(s5, "SA-0006", "COL") == "Blue"


def test_absence_changes_nothing(story):
    """EC3: a product missing from a full load is not retracted; lPR_Product still shows it."""
    s3, s5 = story.snap("s3"), story.snap("s5")
    pid = pr_id(s5, "SG-0004")
    for m in ATTRIBUTES:
        assert annexes(s5, m, pid) == annexes(s3, m, pid), m
    assert latest(s5, "SG-0004", "NAM") == "Gone Bike"
    assert latest(s5, "SG-0004", "COL") == "Silver"


def test_change_back(story):
    """EC4: A, B, A over three loads at later ChangedAts gives three versions; the third A is not a restatement."""
    s5 = story.snap("s5")
    pid = pr_id(s5, "SB-0007")
    assert [(v, d) for _, v, d in posits(s5, "COL", pid)] == [("Blue", D0), ("Yellow", D1), ("Blue", D2)]
    assert all(r[3] == 1 for r in annexes(s5, "COL", pid))
    assert latest(s5, "SB-0007", "COL") == "Blue"


# --------------------------------------------------------------------------- story #4: pPR_Product
#
# pPR_Product(changingTimepoint) is per identity each attribute's latest reliable positor-0 posit
# with ChangedAt at or before the changing time; before an attribute's first ChangedAt it shows no
# value, while serve backfills the first value to 0001-01-01.

# Every ChangedAt of the story lake is a midnight: M0, M1, M2 above.
STORY_LABELS = ("s1", "s2", "s3", "s4", "s5", "s6", "s7")
DATE_MNEMONICS = ("SST", "SEN", "DIS")


def _text(mnemonic: str, value):
    """An attribute value as comparable text: dates by their day, whatever type integrate keeps."""
    if value is None:
        return None
    return str(value)[:10] if mnemonic in DATE_MNEMONICS else str(value)


def _pit_value(snap: Snapshot, rows: dict, number: str, mnemonic: str):
    record = rows.get(pr_id(snap, number))
    assert record is not None, f"pPR has no row for {number}"
    return _text(mnemonic, record[attribute(mnemonic)])


def _attribute_columns(columns: list[str]) -> list[str]:
    """pPR's columns that belong to one attribute, not to the anchor (PR_ID, Metadata_PR)."""
    return [c for c in columns if c not in ("PR_ID", "Metadata_PR")]


def test_pit_shape(story, business):
    """AC1, EC4: after every build, pPR_Product runs with a timestamp, a date and current_date and returns
    exactly lPR_Product's column names, in order; a date gives the rows of its midnight timestamp."""
    snaps = [(label, story.snap(label)) for label in STORY_LABELS] + [("business", business)]
    for label, snap in snaps:
        expected = snap.columns("integrate", "lPR_Product")
        assert expected, f"{label}: integrate has no lPR_Product to compare with"
        for when in (at("2014-03-01 00:00:00"), "date '2014-03-01'", "current_date"):
            assert pit_columns(snap, when) == expected, f"{label}: pPR({when}) columns differ from lPR_Product's"
            snap.sql(f"select * from {PIT}({when})")
    snap = story.snap("s5")
    for day in ("2000-01-01", D0, "2014-02-28", D1, "2014-03-31", D2, "2099-01-01"):
        as_date, as_midnight = f"{PIT}(date '{day}')", f"{PIT}({at(day + ' 00:00:00')})"
        for one, other in ((as_date, as_midnight), (as_midnight, as_date)):
            extra = snap.sql(f"select count(*) from (select * from {one} except all select * from {other})")
            assert extra == [(0,)], f"{one} has rows {other} lacks"
        assert snap.sql(f"select count(*) from {as_date}") == [(9,)], day


def test_pit_values(story):
    """AC2, EC2, EC3: on #1's story lake after loads 1 to 5, pPR at chosen times shows each attribute's
    latest reliable posit with ChangedAt at or before the time, inclusive."""
    snap = story.snap("s5")
    cases = [
        # A new value at a later ChangedAt; at exactly a ChangedAt the value posited then shows (EC2).
        ("SC-0001", "COL", "2014-02-07 23:59:59", None),
        ("SC-0001", "COL", D0, "Black"),
        ("SC-0001", "COL", "2014-02-28 23:59:59", "Black"),
        ("SC-0001", "COL", D1, "Red"),
        ("SC-0001", "COL", "2099-01-01", "Red"),
        ("SC-0001", "LIN", D1, "R"),
        # A correction at a held ChangedAt shows the corrected value from that ChangedAt.
        ("SN-0002", "NAM", D0, "Alpha Prime"),
        ("SN-0002", "NAM", "2014-06-01", "Alpha Prime"),
        # A source null retracting the only value: nothing reliable at or before the time (EC3).
        ("SE-0003", "SEN", D0, None),
        ("SE-0003", "SEN", "2014-06-01", None),
        ("SE-0003", "NAM", "2014-06-01", "Ending Bike"),
        # A product first landed in load 3, after load 1 and 2's builds, at ChangedAt M0.
        ("SN-0009", "NAM", "2014-02-07 23:59:59", None),
        ("SN-0009", "NAM", D0, "Newcomer"),
        # A, B, A over three builds and over two loads in one build.
        *[
            (number, "COL", when, color)
            for number in ("SB-0007", "SA-0006")
            for when, color in (
                (D0, "Blue"),
                ("2014-02-28 23:59:59", "Blue"),
                (D1, "Yellow"),
                ("2014-03-31 23:59:59", "Yellow"),
                (D2, "Blue"),
                ("2099-01-01", "Blue"),
            )
        ],
        # A failed cast changes nothing.
        ("SX-0005", "SST", "2014-06-01", "2011-05-31"),
        # Absence from a full load changes nothing.
        ("SG-0004", "NAM", "2014-06-01", "Gone Bike"),
        ("SS-0008", "DIS", "2014-06-01", "2015-01-01"),
    ]
    calls: dict[str, dict] = {}
    wrong = []
    for number, mnemonic, when, expected in cases:
        rows = calls.setdefault(when, pit(snap, at(when)))
        got = _pit_value(snap, rows, number, mnemonic)
        if got != expected:
            wrong.append(f"pPR({when}) {number} {attribute(mnemonic)}: {got!r}, expected {expected!r}")
    assert not wrong, "\n".join(wrong)

    for when, rows in calls.items():
        moment = datetime.fromisoformat(when)
        for record in rows.values():
            for m in ATTRIBUTES:
                changed = record[f"PR_{m}_ChangedAt"]
                if record[attribute(m)] is None and changed is None:
                    continue
                assert changed is not None and changed.replace(tzinfo=None) <= moment, (
                    f"pPR({when}) PR_ID {record['PR_ID']} shows {attribute(m)} from ChangedAt {changed}"
                )
                assert record[f"PR_{m}_Positor"] == 0, record
                assert record[f"PR_{m}_Reliability"] == 1, record

    sst = [c for c in pit_columns(snap, at(D1)) if c.startswith("PR_SST_")]
    s3 = story.snap("s3")
    before = pit(s3, at("2014-06-01"))[pr_id(s3, "SX-0005")]
    after = calls["2014-06-01"][pr_id(snap, "SX-0005")]
    assert {c: after[c] for c in sst} == {c: before[c] for c in sst}, "the failed cast changed pPR's sell start"


def test_pit_equals_latest(story, business):
    """AC3: pPR at a time after every ChangedAt equals lPR_Product row for row."""
    for label, snap in (("s5", story.snap("s5")), ("s7", story.snap("s7")), ("business", business)):
        latest_rows = "select * from integrate.lPR_Product"
        point = f"select * from {PIT}({at('2099-01-01')})"
        for one, other in ((latest_rows, point), (point, latest_rows)):
            extra = snap.sql(f"select count(*) from ({one} except all {other})")
            assert extra == [(0,)], f"{label}: `{one}` has rows `{other}` lacks"
        count = snap.count("integrate", "lPR_Product")
        assert count > 0, label
        assert snap.sql(f"select count(*) from ({point})") == [(count,)], label


def test_pit_no_backfill(story, business):
    """AC4, EC1: before every ChangedAt, pPR returns one row per PR_Product identity with every attribute
    column null, while serve's dimension at that date shows the first values; an attribute first known
    later than the others is null in pPR until its own first ChangedAt."""
    snap = story.snap("s5")
    rows = pit(snap, at("2000-01-01"))
    identities = {r[0] for r in snap.sql("select PR_ID from integrate.PR_Product")}
    assert set(rows) == identities and len(identities) == 9
    columns = _attribute_columns(pit_columns(snap, at("2000-01-01")))
    held = [(pid, c, r[c]) for pid, r in rows.items() for c in columns if r[c] is not None]
    assert not held, f"pPR before every ChangedAt holds values: {held[:10]}"

    def serve_on(snap: Snapshot, day: str, number: str, what: str):
        rows = snap.sql(
            f"select cast({q(dimension_column(snap, what))} as varchar) from serve__uss.product "
            "where split_part(_key__product, '|', 1) = ? "
            f"and product__valid_from <= {at(day)} and {at(day)} < product__valid_to",
            [str(pr_id(snap, number))],
        )
        assert len(rows) == 1, f"serve__uss.product has {len(rows)} versions of {number} on {day}"
        return rows[0][0]

    expected = [
        ("SC-0001", "color", "Black"),
        ("SN-0002", "name", "Alpha Prime"),
        ("SA-0006", "color", "Blue"),
        ("SS-0008", "discontinued", "2015-01-01"),
        ("SN-0009", "name", "Newcomer"),
    ]
    for number, what, value in expected:
        got = serve_on(snap, "2000-01-01", number, what)
        assert (got or "")[: len(value)] == value, f"serve on 2000-01-01, {number} {what}: {got!r}"
    for number in [*base_products(), "SN-0009"]:
        assert serve_on(snap, "2000-01-01", number, "number") == number

    # BQ-104's discontinued date is first posited at LATE_CHANGE, a year after its other attributes.
    pid = pr_id(business, "BQ-104")
    between = pit(business, at("2012-06-01"))[pid]
    assert between[attribute("NUM")] == "BQ-104"
    assert between[attribute("COL")] == "Red"
    assert between[attribute("DIS")] is None, between
    assert _text("DIS", pit(business, at(LATE_CHANGE))[pid][attribute("DIS")]) == LATE_DISCONTINUED
    assert (serve_on(business, "2012-06-01", "BQ-104", "discontinued") or "")[:10] == LATE_DISCONTINUED


# --------------------------------------------------------------------------- AC4, EC5


def business_products() -> list[dict]:
    """Products with one version each, from 0001-01-01, so D = 2013-06-01 falls in it."""
    m = "2012-01-01"
    early = "2011-05-31"
    late = "2013-07-01"
    return [
        product(101, "BQ-101", "On sale R Black", line="R ", color="Black", sell_start=early, modified=m),
        product(
            102,
            "BQ-102",
            "Ends on D",
            line="R",
            color="Black",
            sell_start=early,
            sell_end="2013-06-01",
            modified=m,
        ),
        product(
            103, "BQ-103", "Starts on D", line="R", color="Red", sell_start="2013-06-01", modified=m
        ),
        product(
            104,
            "BQ-104",
            "Starts after D",
            line="M",
            color="Red",
            sell_start="2013-06-02",
            modified=m,
        ),
        # AC16: BQ-104 again, discontinued first known at a later ChangedAt than its other attributes.
        product(
            104,
            "BQ-104",
            "Starts after D",
            line="M",
            color="Red",
            sell_start="2013-06-02",
            discontinued=LATE_DISCONTINUED,
            modified=LATE_CHANGE,
        ),
        product(
            105,
            "BQ-105",
            "Ended before D",
            line="M",
            color="Red",
            sell_start=early,
            sell_end="2013-05-31",
            modified=m,
        ),
        product(
            106,
            "BQ-106",
            "Discontinued on D",
            line="M",
            color="Red",
            sell_start=early,
            discontinued="2013-06-01",
            modified=m,
        ),
        product(
            107,
            "BQ-107",
            "Discontinued after D",
            line="M",
            color="Red",
            sell_start=early,
            discontinued="2013-06-02",
            modified=m,
        ),
        product(108, "BQ-108", "Null line", line=None, color="Silver", sell_start=early, modified=m),
        product(109, "BQ-109", "Blank line", line="  ", color="Silver", sell_start=early, modified=m),
        product(110, "BQ-110", "Null line and colour", line=None, color=None, sell_start=early, modified=m),
        # F5: one product twice in the load, same values at two ChangedAts, in either row order.
        # They go on sale after D, so the business question does not count them.
        *_restated(201, "RS-201", later_first=True),
        *_restated(202, "RS-202", later_first=False),
        # F6: no usable ModifiedDate.
        product(203, "NM-203", "No modified", line="T", color="White", sell_start=late, modified=None),
        product(204, "NM-204", "Bad modified", line="T", color="White", sell_start=late, modified="n/a"),
    ]


RESTATED_T1, RESTATED_T2 = "2012-01-01", "2012-06-01"
LATE_CHANGE, LATE_DISCONTINUED = "2013-01-01", "2014-01-01"


def _restated(product_id: int, number: str, *, later_first: bool) -> list[dict]:
    rows = [
        product(product_id, number, "Restated", line="T", color="White", sell_start="2013-07-01", modified=t)
        for t in (RESTATED_T1, RESTATED_T2)
    ]
    return rows[::-1] if later_first else rows


@pytest.fixture(scope="module")
def business_workspace(make_workspace) -> tuple[Workspace, Snapshot]:
    ws = make_workspace("business")
    ws.write_load(1, business_products())
    require(ws.generate())
    step = require(ws.build())
    return ws, ws.snapshot("built", step)


@pytest.fixture(scope="module")
def business(business_workspace) -> Snapshot:
    return business_workspace[1]


def test_business_question(business):
    """AC4, EC5: products on sale on 2013-06-01 per product line and colour, read from each product's version
    valid on that day; null and blank lines are their own groups."""
    snap = business
    line, color = dimension_column(snap, "line"), dimension_column(snap, "color")
    start, end, disc = (dimension_column(snap, w) for w in ("sell_start", "sell_end", "discontinued"))
    d = "date '2013-06-01'"
    rows = snap.sql(
        f"select {q(line)}, {q(color)}, count(*) from serve__uss.product "
        "where _key__product like '%|%' "
        f"and cast(product__valid_from as date) <= {d} and {d} < cast(product__valid_to as date) "
        f"and cast({q(start)} as date) <= {d} "
        f"and ({q(end)} is null or cast({q(end)} as date) >= {d}) "
        f"and ({q(disc)} is null or {d} < cast({q(disc)} as date)) "
        "group by all"
    )
    assert sorted(rows, key=repr) == sorted(
        [
            ("R", "Black", 2),
            ("R", "Red", 1),
            ("M", "Red", 1),
            (None, "Silver", 1),
            ("", "Silver", 1),
            (None, None, 1),
        ],
        key=repr,
    )
    assert {"stage", "_key__product", "_valid_from", "_valid_to"} <= set(
        snap.columns("serve__uss", "_bridge")
    )
    assert snap.count("serve__uss", "_bridge") > 0
    assert latest(snap, "BQ-109", "LIN") == ""
    assert latest(snap, "BQ-108", "LIN") is None


def test_first_version_holds_a_later_first_value(business):
    """AC16: an attribute first known at a later ChangedAt than the others shows its earliest value in the
    first version, from 0001-01-01; holding it from then is no change, so there is no second version."""
    snap = business
    pid = pr_id(snap, "BQ-104")
    assert [d for _, _, d in posits(snap, "NUM", pid)] == ["2012-01-01"]
    assert [(v, d) for _, v, d in posits(snap, "DIS", pid)] == [(LATE_DISCONTINUED, LATE_CHANGE)]
    attrs, versions = _dimension_versions(snap)
    disc = attrs.index(dimension_column(snap, "discontinued")) + 4
    color = attrs.index(dimension_column(snap, "color")) + 4
    got = [(v[2], v[3], (v[disc] or "")[:10], v[color]) for v in versions[str(pid)]]
    assert got == [("0001-01-01", "9999-12-31", LATE_DISCONTINUED, "Red")]


def test_restatement_within_one_load(business):
    """F5: two rows of one product in one load with the same values at t1 < t2 give one posit at t1, in either row order."""
    snap = business
    for number in ("RS-201", "RS-202"):
        pid = pr_id(snap, number)
        for m in ("NUM", "NAM", "LIN", "COL", "SST"):
            got = posits(snap, m, pid)
            assert [d for _, _, d in got] == [RESTATED_T1], f"{number} {m}: {got}"
            assert [r[3] for r in annexes(snap, m, pid)] == [1], f"{number} {m}: {annexes(snap, m, pid)}"
        assert latest(snap, number, "COL") == "White"


def test_no_changed_at_no_identity(business):
    """F6: a product whose ModifiedDate is null, or fails its cast, gets no PR_Product identity and no dimension row."""
    snap = business
    numbers = ("NM-203", "NM-204")
    value = q(attribute("NUM"))
    posited = snap.sql(
        f"select {value} from integrate.{q(posit('NUM'))} where {value} in (?, ?)", list(numbers)
    )
    assert posited == []
    known = {r[0] for r in snap.sql(f"select {value} from integrate.{q(posit('NUM'))}")}
    assert snap.count("integrate", "PR_Product") == len(known) == 12
    number = dimension_column(snap, "number")
    rows = snap.sql(f"select count(*) from serve__uss.product where {q(number)} in (?, ?)", list(numbers))
    assert rows == [(0,)]


def test_contradiction_fails_the_build_new_row_first(business_workspace):
    """ADR-0006: a load holding a held version and another value at the same ChangedAt fails the build,
    with the new value's row first and the row repeating load 1 second."""
    ws, _ = business_workspace
    held = next(p for p in business_products() if p["ProductNumber"] == "BQ-101")
    ws.write_load(2, [dict(held, Color="Purple"), held])
    step = ws.build()
    assert step.returncode != 0, f"the contradicting load built:\n{tail(step.output)}"
    assert CONTRADICTION in step.output, f"the build failed for another reason:\n{tail(step.output)}"


# --------------------------------------------------------------------------- EC1


def test_empty_lake(make_workspace):
    """EC1: with no Products folder, dbt build exits 0; conform and every Anchor table are empty; the dimension holds only the ghosts."""
    ws = make_workspace("empty")
    require(ws.generate())
    snap = ws.snapshot("built", require(ws.build()))
    for name in snap.relations("conform"):
        assert snap.count("conform", name) == 0, name
    assert snap.count("integrate", "PR_Product") == 0
    for m in ATTRIBUTES:
        assert snap.count("integrate", posit(m)) == 0
        assert snap.count("integrate", annex(m)) == 0
    assert snap.count("serve__uss", "product") == 2
    assert ghost_rows(snap) == {g: 1 for g in GHOSTS}


# --------------------------------------------------------------------------- EC7


def _break_one_integrate_model(ws: Workspace):
    """Make one generated integrate model raise when it runs, and return a function that undoes it."""
    models = sorted((ws.root / "models" / "integrate").rglob("*.sql"))
    assert models, "no generated integrate models"
    ranked = sorted(
        models,
        key=lambda p: ("pr_col" not in p.name.lower(), "annex" not in p.name.lower(), p.name),
    )
    target = ranked[0]
    original = target.read_text()
    target.write_text(
        original + "\n{% if execute %}{{ exceptions.raise_compiler_error('forced failure') }}{% endif %}\n"
    )
    return lambda: target.write_text(original)


def test_recovery_after_failed_build(make_workspace):
    """EC7: a build that fails after conform committed leaves no SUCCEEDED batch; the next build applies the staged load."""
    ws = make_workspace("recovery")
    first = base_products()
    rows = [first["SC-0001"], first["SN-0002"]]
    ws.write_load(1, rows)
    require(ws.generate())
    before = ws.snapshot("before", require(ws.build()))

    changed = [dict(first["SC-0001"], Color="Red", ModifiedDate=M1), first["SN-0002"]]
    ws.write_load(2, changed)
    restore = _break_one_integrate_model(ws)
    failed_step = ws.build()
    restore()
    assert failed_step.returncode != 0, "the forced failure did not fail the build"
    failed = ws.snapshot("failed", failed_step)
    staged = failed.staged()
    assert failed.count("conform", staged) == 4, "conform should have committed load 2 before the failure"
    added = [b for b in failed.load_log() if b not in before.load_log()]
    assert all(status == "RUNNING" for _, status in added), added

    recovered = ws.snapshot("recovered", require(ws.build()))
    added = [b for b in recovered.load_log() if b not in failed.load_log()]
    assert [status for _, status in added] == ["SUCCEEDED"]
    pid = pr_id(recovered, "SC-0001")
    assert [(v, d) for _, v, d in posits(recovered, "COL", pid)] == [("Black", D0), ("Red", D1)]
    assert [(r[1], r[3]) for r in annexes(recovered, "COL", pid)] == [(epoch_us(L1), 1), (epoch_us(L2), 1)]
    assert latest(recovered, "SC-0001", "COL") == "Red"
    for m in ATTRIBUTES:
        if m != "COL":
            assert annexes(recovered, m, pid) == annexes(before, m, pid), m
    assert integrity_violations(recovered) == 0

    # ADR-0007: a failing IntegrityViolations does not hold a batch open; it closes VIOLATIONS.
    # No load produces a violation, so one annex row of SN-0002's name is duplicated by hand.
    import duckdb

    con = duckdb.connect(str(ws.warehouse))
    try:
        con.execute(
            f"insert into integrate.{q(annex('NAM'))} select * from integrate.{q(annex('NAM'))} a "
            f"where a.PR_NAM_ID in (select PR_NAM_ID from integrate.{q(posit('NAM'))} where PR_NAM_PR_ID = ?) "
            "limit 1",
            [pr_id(recovered, "SN-0002")],
        )
    finally:
        con.close()
    ws.write_load(3, [dict(first["SC-0001"], Color="Green", ModifiedDate=M2), first["SN-0002"]])
    violated_step = ws.build()
    violated = ws.snapshot("violated", violated_step)
    assert integrity_violations(violated) > 0, "the duplicated annex row is not an integrity violation"
    known = {b for b, _ in recovered.load_log()}
    added = [b for b in violated.load_log() if b[0] not in known]
    assert [status for _, status in added] == ["VIOLATIONS"], (
        f"load log after the build: {violated.load_log()}\n{tail(violated_step.output)}"
    )
    assert [b for b in violated.load_log() if b[1] == "RUNNING"] == []


# --------------------------------------------------------------------------- F3, F4
#
#   l1  load 1: LC-0001 Black at D0, LC-0002 steady          build
#   l2  load 2: LC-0001 Red at D1                             build
#   l3  loads 3 and 4, identical to load 2                    build
#   l4  load 5, identical to load 2                           build
#   l5  load 6: LC-0001 Green at D2                           build --exclude path:models/serve
#   l6  no new files                                          build
#   l7  load 7: LC-0002 twice at its held ChangedAt, its held
#       Silver first, then Gold: a contradiction        build (must fail)


def lifecycle_load(color: str, modified: str) -> list[dict]:
    return [
        product(301, "LC-0001", "Changing Bike", color=color, modified=modified),
        product(302, "LC-0002", "Steady Bike", color="Silver"),
    ]


@pytest.fixture(scope="module")
def lifecycle(make_workspace) -> Story:
    ws = make_workspace("lifecycle")
    s = Story(ws)
    ws.write_load(1, lifecycle_load("Black", M0))
    if not (s.generate() and s.build("l1")):
        return s
    ws.write_load(2, lifecycle_load("Red", M1))
    if not s.build("l2"):
        return s
    ws.write_load(3, lifecycle_load("Red", M1))
    ws.write_load(4, lifecycle_load("Red", M1))
    if not s.build("l3"):
        return s
    ws.write_load(5, lifecycle_load("Red", M1))
    if not s.build("l4"):
        return s
    ws.write_load(6, lifecycle_load("Green", M2))
    if s.build("l5", "--exclude", "path:models/serve") and s.build("l6"):
        held = lifecycle_load("Green", M2)[1]
        ws.write_load(7, [held, dict(held, Color="Gold")])
        s.contradiction = ws.build()
    return s


def test_unchanged_loads_add_nothing(lifecycle):
    """F4: after one change, three identical loads add no posit or annex; a later change applies as one new version."""
    l2, l3, l4, l5 = (lifecycle.snap(f"l{n}") for n in range(2, 6))
    sizes = {
        label: {t: snap.count("integrate", t) for m in ATTRIBUTES for t in (posit(m), annex(m))}
        for label, snap in (("l2", l2), ("l3", l3), ("l4", l4))
    }
    assert sizes["l3"] == sizes["l2"]
    assert sizes["l4"] == sizes["l2"]
    pid = pr_id(l4, "LC-0001")
    assert [(v, d) for _, v, d in posits(l4, "COL", pid)] == [("Black", D0), ("Red", D1)]
    assert [(r[1], r[3]) for r in annexes(l4, "COL", pid)] == [(epoch_us(L1), 1), (epoch_us(L2), 1)]

    assert [(v, d) for _, v, d in posits(l5, "COL", pid)] == [("Black", D0), ("Red", D1), ("Green", D2)]
    assert [(r[1], r[3]) for r in annexes(l5, "COL", pid)] == [
        (epoch_us(L1), 1),
        (epoch_us(L2), 1),
        (epoch_us(load_id(6)), 1),
    ]
    grown = {t: l5.count("integrate", t) - n for t, n in sizes["l4"].items()}
    assert grown == {t: int(t in (posit("COL"), annex("COL"))) for t in grown}
    assert latest(l5, "LC-0001", "COL") == "Green"


def test_full_build_closes_running_batches(lifecycle):
    """ADR-0007: a batch left RUNNING by a build that excluded serve is closed by the next build of all of serve."""
    l5, l6 = lifecycle.snap("l5"), lifecycle.snap("l6")
    assert "RUNNING" in [status for _, status in l5.load_log()], l5.load_log()
    running = [b for b in l6.load_log() if b[1] == "RUNNING"]
    assert running == [], f"batches still RUNNING after a full build: {running}"


def _contradiction(story: Story):
    step = getattr(story, "contradiction", None)
    if step is None:
        pytest.fail(f"the contradicting load was never built: {story.failure}")
    return step


def test_contradiction_fails_the_build_held_row_first(lifecycle):
    """ADR-0006: two assertions of one version at one PositedAt fail the build, even when the first repeats the previous load."""
    step = _contradiction(lifecycle)
    assert step.returncode != 0, f"the contradicting load built:\n{tail(step.output)}"
    assert CONTRADICTION in step.output, f"the build failed for another reason:\n{tail(step.output)}"


def test_serve_catches_up_after_skipped_build(lifecycle):
    """F3: a build that skipped serve after a change is picked up by the next build: the dimension shows the change."""
    snap = lifecycle.snap("l6")
    pid = str(pr_id(snap, "LC-0001"))
    color = dimension_column(snap, "color")
    versions = snap.sql(
        "select cast(cast(product__valid_from as date) as varchar), "
        f"cast(cast(product__valid_to as date) as varchar), {q(color)} from serve__uss.product "
        "where split_part(_key__product, '|', 1) = ? order by 1",
        [pid],
    )
    assert [(f, c) for f, _, c in versions] == [
        ("0001-01-01", "Black"),
        (D1, "Red"),
        (D2, "Green"),
    ]
    assert versions[-1][1] == "9999-12-31"
    bridged = snap.sql(
        "select count(*) from serve__uss._bridge b join serve__uss.product p using (_key__product) "
        f"where split_part(p._key__product, '|', 1) = ? and p.{q(color)} = 'Green'",
        [pid],
    )
    assert bridged[0][0] > 0, "the bridge has no row for the new version"


# --------------------------------------------------------------------------- story #5: tPR_Product
#
# tPR_Product(changingTimepoint, positingTimepoint) is pPR_Product as known at the positing time K:
# an annex row counts when its PositedAt <= K, a posit when its ChangedAt <= T; per posit its latest
# annex row known at K decides whether it holds; every anchor row is returned. PositedAt is a load's
# _dlt__extracted_at, so K is named by load: posited(L3) is L3's PositedAt, posited(L3, -1) one
# microsecond before it.

T0 = at(D0)
FAR = "date '9999-12-31'"
DAY_US = 86_400_000_000
# The last load each story build had seen.
LATEST_LOAD = {"s1": L1, "s2": L1, "s3": L2, "s4": L3, "s5": L5, "s6": L5, "s7": L5}


def _moment_of(literal: str) -> datetime:
    """The naive datetime a ``date '...'`` or ``timestamp '...'`` literal names."""
    return datetime.fromisoformat(literal.split("'")[1])


def _epoch_us_of(value: datetime) -> int:
    """A PositedAt as epoch microseconds, as ``epoch_us`` gives a load's."""
    naive = value.replace(tzinfo=None) if value.tzinfo is None else value.astimezone(UTC).replace(tzinfo=None)
    delta = naive - datetime(1970, 1, 1)
    return (delta.days * 86_400 + delta.seconds) * 1_000_000 + delta.microseconds


def _tt_value(snap: Snapshot, rows: dict, number: str, mnemonic: str):
    record = rows.get(pr_id(snap, number))
    assert record is not None, f"tPR has no row for {number}"
    return _text(mnemonic, record[attribute(mnemonic)])


def _known_at_holds(rows: dict, changing: str, positing: str) -> list[str]:
    """What breaks crt's rules in tPR's rows: a value changed after T, posited after K, or not reliable positor 0."""
    t, k = _moment_of(changing), _moment_of(positing)
    broken = []
    for record in rows.values():
        for m in ATTRIBUTES:
            if record[attribute(m)] is None and record[f"PR_{m}_ChangedAt"] is None:
                continue
            changed, stated = record[f"PR_{m}_ChangedAt"], record[f"PR_{m}_PositedAt"]
            if changed is None or changed.replace(tzinfo=None) > t:
                broken.append(f"PR_ID {record['PR_ID']} {attribute(m)} from ChangedAt {changed} > T {t}")
            if stated is None or stated.replace(tzinfo=None) > k:
                broken.append(f"PR_ID {record['PR_ID']} {attribute(m)} posited at {stated} > K {k}")
            if (record[f"PR_{m}_Positor"], record[f"PR_{m}_Reliability"]) != (0, 1):
                broken.append(f"PR_ID {record['PR_ID']} {attribute(m)} is not reliable positor 0: {record}")
    return broken


def _same_rows(snap: Snapshot, one: str, other: str) -> list[str]:
    """Both ways of ``except all`` between two queries, and their counts: empty when they hold the same rows."""
    found = []
    for a, b in ((one, other), (other, one)):
        extra = snap.sql(f"select count(*) from ({a} except all {b})")[0][0]
        if extra:
            found.append(f"`{a}` has {extra} rows `{b}` lacks")
    return found


def test_tt_shape(story):
    """Story #5 AC1: after every story build, tPR_Product runs with a date or a timestamp for either argument
    and returns exactly lPR_Product's column names, in order."""
    calls = (
        ("date '2014-03-01'", "date '2099-01-01'"),
        (at("2014-03-01 00:00:00"), posited(L1)),
        ("date '2014-03-01'", posited(L1)),
        (at("2014-03-01 00:00:00"), "date '2099-01-01'"),
    )
    for label in STORY_LABELS:
        snap = story.snap(label)
        expected = snap.columns("integrate", "lPR_Product")
        assert expected, f"{label}: integrate has no lPR_Product to compare with"
        for changing, positing in calls:
            got = tt_columns(snap, changing, positing)
            assert got == expected, f"{label}: tPR({changing}, {positing}) columns differ from lPR_Product's"
            assert snap.sql(f"select count(*) from {TT}({changing}, {positing})")[0][0] > 0, label


def test_tt_correction(story):
    """Story #5 AC2, EC2, EC6: in s4, SN-0002's name at T0 is Alpha as known at L2 and just before L3, and
    Alpha Prime as known exactly at L3 and after it; SX-0005's failed cast in L3 changes its sell start as
    known at none of those K."""
    snap = story.snap("s4")
    cases = [
        (posited(L2), "Alpha"),
        (posited(L3, -1), "Alpha"),
        (posited(L3), "Alpha Prime"),
        (posited(L3, DAY_US), "Alpha Prime"),
    ]
    wrong, sell_starts = [], []
    sst = [c for c in tt_columns(snap, T0, posited(L3)) if c.startswith("PR_SST_")]
    for positing, expected in cases:
        rows = tt(snap, T0, positing)
        got = _tt_value(snap, rows, "SN-0002", "NAM")
        if got != expected:
            wrong.append(f"tPR(T0, {positing}) SN-0002 name: {got!r}, expected {expected!r}")
        wrong += _known_at_holds(rows, T0, positing)
        record = rows[pr_id(snap, "SX-0005")]
        sell_starts.append({c: record[c] for c in sst})
        if _text("SST", record[attribute("SST")]) != "2011-05-31":
            wrong.append(f"tPR(T0, {positing}) SX-0005 sell start: {record[attribute('SST')]!r}")
    assert not wrong, "\n".join(wrong)
    assert all(s == sell_starts[0] for s in sell_starts), f"SX-0005's sell start moves with K: {sell_starts}"

    corrected = tt(snap, T0, posited(L3))[pr_id(snap, "SN-0002")]
    assert _epoch_us_of(corrected["PR_NAM_PositedAt"]) == epoch_us(L3), corrected


def test_tt_retraction(story):
    """Story #5 AC3: a source null retracts from its PositedAt: in s4, SE-0003's sell end at T0 is
    2013-05-29 as known just before L3, and null as known at L3 and after."""
    snap = story.snap("s4")
    cases = [
        (posited(L1), "2013-05-29"),
        (posited(L3, -1), "2013-05-29"),
        (posited(L3), None),
        (posited(L3, DAY_US), None),
        (FAR, None),
    ]
    wrong = []
    for positing, expected in cases:
        rows = tt(snap, T0, positing)
        got = _tt_value(snap, rows, "SE-0003", "SEN")
        if got != expected:
            wrong.append(f"tPR(T0, {positing}) SE-0003 sell end: {got!r}, expected {expected!r}")
        if _tt_value(snap, rows, "SE-0003", "NAM") != "Ending Bike":
            wrong.append(f"tPR(T0, {positing}) SE-0003 lost its name with its sell end")
    assert not wrong, "\n".join(wrong)


def test_tt_equals_pit(story):
    """Story #5 AC4, EC4: after every story build, tPR(T, K) with K at or after the latest load's PositedAt
    equals pPR(T) row for row, for the T's test_pit_values uses."""
    times = (
        "2000-01-01",
        "2014-02-07 23:59:59",
        D0,
        "2014-02-28 23:59:59",
        D1,
        "2014-03-31 23:59:59",
        D2,
        "2014-06-01",
        "2099-01-01",
    )
    wrong = []
    for label in STORY_LABELS:
        snap = story.snap(label)
        for when in times:
            point = f"select * from {PIT}({at(when)})"
            count = snap.sql(f"select count(*) from ({point})")[0][0]
            assert count > 0, f"{label}: pPR({when}) is empty"
            for positing in (FAR, posited(LATEST_LOAD[label])):
                known = f"select * from {TT}({at(when)}, {positing})"
                wrong += [f"{label}: {w}" for w in _same_rows(snap, known, point)]
    assert not wrong, "\n".join(wrong[:20])


def test_tt_before_first_load(story):
    """Story #5 EC1: as known before L1's PositedAt, tPR returns every identity with an anchor row and every
    attribute column null; an identity first posited in L3 is returned, all null, as known before L3."""
    for label, positing in (("s1", posited(L1, -1)), ("s5", posited(L1, -1)), ("s5", "date '2000-01-01'")):
        snap = story.snap(label)
        rows = tt(snap, T0, positing)
        identities = {r[0] for r in snap.sql("select PR_ID from integrate.PR_Product")}
        assert identities, f"{label}: PR_Product is empty"
        assert set(rows) == identities, f"{label}: tPR(T0, {positing}) returns {sorted(rows)}, PR_Product holds {sorted(identities)}"
        columns = _attribute_columns(tt_columns(snap, T0, positing))
        held = [(pid, c, r[c]) for pid, r in rows.items() for c in columns if r[c] is not None]
        assert not held, f"{label}: tPR(T0, {positing}) holds values: {held[:10]}"

    snap = story.snap("s4")
    rows = tt(snap, at("2099-01-01"), posited(L3, -1))
    newcomer = rows.get(pr_id(snap, "SN-0009"))
    assert newcomer is not None, "tPR as known before L3 drops SN-0009, whose anchor row exists"
    columns = _attribute_columns(list(newcomer))
    assert all(newcomer[c] is None for c in columns), newcomer
    assert _tt_value(snap, rows, "SN-0002", "NAM") == "Alpha"


def test_tt_one_build_two_loads(story):
    """Story #5 EC3: loads 4 and 5 applied in one build keep their own PositedAts: in s5, SA-0006's colour at
    2014-04-01 is Blue as known before L4, Yellow between L4 and L5, and Blue from L5 on."""
    snap = story.snap("s5")
    when = at(D2)
    cases = [
        (posited(L4, -1), "Blue"),
        (posited(L4), "Yellow"),
        (posited(L5, -1), "Yellow"),
        (posited(L5), "Blue"),
        (FAR, "Blue"),
    ]
    wrong = []
    for positing, expected in cases:
        rows = tt(snap, when, positing)
        got = _tt_value(snap, rows, "SA-0006", "COL")
        if got != expected:
            wrong.append(f"tPR({D2}, {positing}) SA-0006 colour: {got!r}, expected {expected!r}")
        wrong += _known_at_holds(rows, when, positing)
    assert not wrong, "\n".join(wrong)
    yellow = tt(snap, when, posited(L5, -1))[pr_id(snap, "SA-0006")]
    assert _epoch_us_of(yellow["PR_COL_PositedAt"]) == epoch_us(L4), yellow


# --------------------------------------------------------------------------- story #5 AC5
#
# The story's first three loads again, with SN-0002 named Alpha Prime from L1 on: no correction is
# ever posited. Serve reads current knowledge, so it holds the same rows as the story at s4.


def corrected_from_start() -> dict[str, dict]:
    rows = base_products()
    rows["SN-0002"].update(Name="Alpha Prime")
    return rows


@pytest.fixture(scope="module")
def uncorrected(make_workspace) -> Story:
    ws = make_workspace("uncorrected")
    s = Story(ws)
    ws.write_load(1, list(corrected_from_start().values()))
    if not (s.generate() and s.build("s1") and s.build("s2")):
        return s
    ws.write_load(2, list(corrected_from_start().values()))
    if not s.build("s3"):
        return s
    ws.write_load(3, list(load_3().values()))
    s.build("s4")
    return s


SERVED = (("serve__uss", "product"), ("serve__uss", "_bridge"), ("serve__uss_staging", "bridge__product"))


def test_serve_ignores_positing(story, uncorrected):
    """Story #5 AC5: serve's product, _bridge and bridge__product hold the same rows after L3 whether SN-0002
    was Alpha and corrected in L3, or Alpha Prime from L1."""
    corrected, plain = story.snap("s4"), uncorrected.snap("s4")
    names = {v for _, v, _ in posits(corrected, "NAM", pr_id(corrected, "SN-0002"))}
    assert names == {"Alpha", "Alpha Prime"}, f"the story posited no correction to compare: {names}"
    names = {v for _, v, _ in posits(plain, "NAM", pr_id(plain, "SN-0002"))}
    assert names == {"Alpha Prime"}, f"the uncorrected run posited {names}"
    for schema, relation in SERVED:
        assert corrected.columns(schema, relation) == plain.columns(schema, relation), f"{schema}.{relation}"
        query = f"select * from {q(schema)}.{q(relation)}"
        one, other = corrected.sql(query), plain.sql(query)
        assert one, f"{schema}.{relation} is empty"
        assert sorted(one, key=repr) == sorted(other, key=repr), f"{schema}.{relation} differs with positing"
