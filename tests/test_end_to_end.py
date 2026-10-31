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
"""

from __future__ import annotations

import re

import pytest
import yaml

from harness import (
    ATTRIBUTES,
    CONTRACT,
    GHOSTS,
    SCHEMAS,
    Snapshot,
    Workspace,
    annex,
    annexes,
    attribute,
    dimension_column,
    epoch_us,
    ghost_rows,
    integrity_violations,
    latest,
    load_id,
    posit,
    posits,
    pr_id,
    product,
    q,
    require,
    tail,
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
    """F1: dbt build --full-refresh does not rebuild integrate: every anchor, posit and annex row stays as it was."""
    s6, s7 = story.snap("s6"), story.snap("s7")
    before, after = _anchor_rows(s6), _anchor_rows(s7)
    assert all(before.values()), "the story left an empty integrate table to compare"
    for table in before:
        assert after[table] == before[table], table


# --------------------------------------------------------------------------- AC16, AC17, AC23


def test_dimension_versions(story):
    """AC16: per product an opening version from 0001-01-01 with null attributes, then one version per change, contiguous."""
    snap = story.snap("s5")
    color = dimension_column(snap, "color")
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
        f"cast(cast(product__valid_to as date) as varchar), {q(color)}, "
        + ", ".join(f"{q(c)} is null" for c in attrs)
        + " from serve__uss.product where _key__product like '%|%' order by 1, 4"
    )
    versions: dict[str, list[tuple]] = {}
    for row in rows:
        versions.setdefault(row[0], []).append(row)
    assert len(versions) == 9
    for identity, vs in versions.items():
        assert vs[0][3] == "0001-01-01", (identity, vs[0])
        assert all(vs[0][6:]), f"opening version of {identity} has attributes: {vs[0]}"
        for earlier, later in zip(vs, vs[1:]):
            assert earlier[2] == later[1], f"gap or overlap in {identity}: {earlier} then {later}"
        assert vs[-1][4] == "9999-12-31", (identity, vs[-1])
    by_number = {n: str(pr_id(snap, n)) for n in ("SB-0007", "SC-0001", "SN-0002", "SS-0008")}
    aba = versions[by_number["SB-0007"]]
    assert [(v[3], v[5]) for v in aba] == [("0001-01-01", None), (D0, "Blue"), (D1, "Yellow"), (D2, "Blue")]
    assert [v[3] for v in versions[by_number["SC-0001"]]] == ["0001-01-01", D0, D1]
    assert [v[3] for v in versions[by_number["SN-0002"]]] == ["0001-01-01", D0]
    assert [v[3] for v in versions[by_number["SS-0008"]]] == ["0001-01-01", D0]


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


# --------------------------------------------------------------------------- AC4, EC5


def business_products() -> list[dict]:
    """Products whose every version starts before D = 2013-06-01, so D falls in their one version."""
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
    """AC4, EC5: products on sale on 2013-06-01 per product line and colour; null and blank lines are their own groups."""
    snap = business
    line, color = dimension_column(snap, "line"), dimension_column(snap, "color")
    start, end, disc = (dimension_column(snap, w) for w in ("sell_start", "sell_end", "discontinued"))
    d = "date '2013-06-01'"
    rows = snap.sql(
        f"select {q(line)}, {q(color)}, count(*) from serve__uss.product "
        f"where cast(product__valid_from as date) <= {d} and {d} < cast(product__valid_to as date) "
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
        ("0001-01-01", None),
        (D0, "Black"),
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
