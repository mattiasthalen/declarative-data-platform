"""Story #6 in integrate: the tie PR_in_PS_contains, loaded as an attribute of Product (AC4 to AC8, EC3, EC5).

The story lake is ``tie_story``'s. After its builds, the fixture uses the same workspace twice more,
each from its last build: a duplicate posit written straight into the tie's posit table, then
``dbt test`` (AC4), the warehouse put back after; and a contradicting products load, then ``dbt
build`` (AC8).
"""

from __future__ import annotations

import shutil

import pytest
import tie_story
from harness import (
    Snapshot,
    epoch_us,
    load_id,
    posited,
    pr_id,
    q,
    tail,
    write_load,
)
from tie_story import (
    D0,
    MOVE,
    PRODUCT_ROLE,
    RESTORE,
    SUBCATEGORY_ROLE,
    TIE,
    TIE_ANNEX,
    TIE_POSIT,
    source_ids,
    tie_rows,
)

L1, L2, L3, L5 = (load_id(n) for n in (1, 2, 3, 5))
LATEST = f'integrate."l{TIE}"'
PIT = f'integrate."p{TIE}"'
TT = f'integrate."t{TIE}"'
CONTRADICTING_DAY = "2014-06-01"


class TieStory(tie_story.Story):
    duplicate = None  # the snapshot `dbt test` left, with a duplicate posit in the tie
    contradiction = None  # the snapshot the contradicting build left
    duplicate_failure = contradiction_failure = "it has not run"


def _duplicate_posit(story: TieStory) -> None:
    import duckdb

    ws = story.ws
    kept = ws.root.parent / "warehouse-before-duplicate.duckdb"
    shutil.copy2(ws.warehouse, kept)
    try:
        con = duckdb.connect(str(ws.warehouse))
        try:
            con.execute(f"insert into integrate.{q(TIE_POSIT)} select * from integrate.{q(TIE_POSIT)} limit 1")
        finally:
            con.close()
    except Exception as error:  # noqa: BLE001
        story.duplicate_failure = f"writing a duplicate posit into {TIE_POSIT} failed: {error!r}"
        shutil.copy2(kept, ws.warehouse)
        return
    step = ws.run("uv", "run", "dbt", "test", "--target", "dev")
    story.duplicate = ws.snapshot("duplicate", step)
    story.duplicate.returncode = step.returncode
    shutil.copy2(kept, ws.warehouse)
    wal = ws.warehouse.with_name(ws.warehouse.name + ".wal")
    if wal.exists():
        wal.unlink()


def _contradicting_load(story: TieStory) -> None:
    ws = story.ws
    rows = [dict(r) for r in tie_story.PRODUCT_LOADS[5] if r["ProductNumber"] != "SN-0001"]
    moved = next(r for r in tie_story.PRODUCT_LOADS[5] if r["ProductNumber"] == "SN-0001")
    rows += [
        dict(moved, ProductSubcategoryId=1, ModifiedDate=CONTRADICTING_DAY),
        dict(moved, ProductSubcategoryId=4, ModifiedDate=CONTRADICTING_DAY),
    ]
    write_load(ws.lake, load_id(6), rows)
    step = ws.build()
    story.contradiction = ws.snapshot("contradiction", step)
    story.contradiction.returncode = step.returncode


@pytest.fixture(scope="module")
def story(make_workspace) -> TieStory:
    ws = make_workspace("ties")
    built = tie_story.run(ws)
    s = TieStory(ws)
    s.snaps, s.failure = built.snaps, built.failure
    if "full" in s.snaps:
        _duplicate_posit(s)
        _contradicting_load(s)
    return s


def _posits(snap: Snapshot, number: str) -> list[tuple]:
    """(posit id, subcategory source id, ChangedAt as date text) of one product's tie posits, in id order."""
    by_source = source_ids(snap)
    rows = snap.sql(
        f"select {q(TIE + '_ID')}, {q(SUBCATEGORY_ROLE)}, cast(cast({q(TIE + '_ChangedAt')} as date) as varchar) "
        f"from integrate.{q(TIE_POSIT)} where {q(PRODUCT_ROLE)} = ? order by 1",
        [pr_id(snap, number)],
    )
    return [(i, by_source[s], d) for i, s, d in rows]


def _annexes(snap: Snapshot, number: str) -> list[tuple]:
    """(posit id, PositedAt in epoch microseconds, Positor, Reliability) of one product's tie annex rows."""
    t = TIE
    return snap.sql(
        f"select a.{q(t + '_ID')}, epoch_us(a.{q(t + '_PositedAt')}), a.{q(t + '_Positor')}, a.{q(t + '_Reliability')} "
        f"from integrate.{q(TIE_ANNEX)} a join integrate.{q(TIE_POSIT)} p on p.{q(t + '_ID')} = a.{q(t + '_ID')} "
        f"where p.{q(PRODUCT_ROLE)} = ? order by 1, 2, 4",
        [pr_id(snap, number)],
    )


def _latest(snap: Snapshot) -> dict[str, int]:
    return tie_rows(snap, f"select * from {LATEST}")


def _pit(snap: Snapshot, when: str) -> dict[str, int]:
    return tie_rows(snap, f"select * from {PIT}(timestamp '{when}')")


def _tt(snap: Snapshot, changing: str, positing: str) -> dict[str, int]:
    return tie_rows(snap, f"select * from {TT}(timestamp '{changing}', {positing})")


# --------------------------------------------------------------------------- AC5, EC3, EC5


def test_tie_history(story):
    """AC5, EC3, EC5 ([2] [3] [4]): the tie's tables and perspectives exist; lPR_in_PS_contains after L3
    gives SN-0001 -> 2, SN-0004 -> 3, no row for SN-0002 or SN-0003; pPR_in_PS_contains('2014-02-20')
    gives SN-0001 -> 1 and SN-0003 -> 2 before L3's retraction; ChangedAt is the row's ModifiedDate and
    PositedAt its load's. A restatement at a later ChangedAt adds no posit; a failed cast changes nothing."""
    s2, s3, s5 = story.snap("L2"), story.snap("L3"), story.snap("L5")
    names = set(s3.relations("integrate"))
    expected = {"PS_ProductSubcategory", TIE, TIE_POSIT, TIE_ANNEX, f"l{TIE}", f"ic_{TIE}", f"ic_{TIE_POSIT}", f"ic_{TIE_ANNEX}"}
    assert expected <= names, f"missing from integrate: {sorted(expected - names)}"
    assert {f"{TIE}_ID", PRODUCT_ROLE, SUBCATEGORY_ROLE, f"{TIE}_ChangedAt"} <= set(s3.columns("integrate", TIE_POSIT))
    assert {f"{TIE}_ID", f"{TIE}_PositedAt", f"{TIE}_Positor", f"{TIE}_Reliability", f"Metadata_{TIE}"} <= set(
        s3.columns("integrate", TIE_ANNEX)
    )

    assert _latest(s3) == {"SN-0001": 2, "SN-0004": 3, "SN-0005": 1, "SN-0006": 2}
    assert _pit(s2, "2014-02-20") == {"SN-0001": 1, "SN-0003": 2, "SN-0004": 3, "SN-0005": 1, "SN-0006": 2}
    assert _pit(s3, "2014-02-20") == {"SN-0001": 1, "SN-0004": 3, "SN-0005": 1, "SN-0006": 2}
    assert _pit(s3, D0)["SN-0001"] == 1, "pPR at exactly a ChangedAt does not show the version posited then"
    assert _pit(s3, "2014-02-07 23:59:59") == {}, "pPR shows a tie version before its ChangedAt"
    assert _pit(s3, "2014-03-15")["SN-0001"] == 2

    # [3]: ChangedAt is the product row's modified_date, PositedAt its load's extraction time.
    assert [(v, d) for _, v, d in _posits(s3, "SN-0001")] == [(1, D0), (2, MOVE)]
    assert [(r[1], r[2], r[3]) for r in _annexes(s3, "SN-0001")] == [(epoch_us(L1), 0, 1), (epoch_us(L3), 0, 1)]
    assert _posits(s3, "SN-0002") == [] and _annexes(s3, "SN-0002") == []

    # EC3: SN-0005 restated in 1 at 2014-03-01 adds no posit and no annex row.
    assert [(v, d) for _, v, d in _posits(s3, "SN-0005")] == [(1, D0)]
    assert _annexes(s3, "SN-0005") == _annexes(s2, "SN-0005")

    # EC5: SN-0006's "n/a" fails its cast in conform and changes nothing in the tie.
    staged = s3.staged()
    failed = s3.sql(
        f"select _contract__cast_failed from conform.{q(staged)} where product_number = ? and _dlt__load_id = ?",
        ["SN-0006", L3],
    )
    assert failed == [(["product_subcategory_id"],)], f"SN-0006's subcategory did not fail its cast: {failed}"
    for snap in (s3, s5):
        assert _posits(snap, "SN-0006") == _posits(s2, "SN-0006")
        assert _annexes(snap, "SN-0006") == _annexes(s2, "SN-0006")
        assert _latest(snap)["SN-0006"] == 2


# --------------------------------------------------------------------------- AC6, EC4


def test_tie_retraction(story):
    """AC6, EC4 ([4]): SN-0003's subcategory nulled in L3 retracts its version (an annex row at reliability 0
    at L3's PositedAt); tPR_in_PS_contains(2014-02-20, just before L3) still gives SN-0003 -> 2. Restored in
    L5 at 2014-05-01, it is missing only as known between L3 and L5."""
    s2, s3, s4, s5 = (story.snap(label) for label in ("L2", "L3", "L4", "L5"))
    assert [(v, d) for _, v, d in _posits(s3, "SN-0003")] == [(2, D0)]
    held = _posits(s3, "SN-0003")[0][0]
    new = [r for r in _annexes(s3, "SN-0003") if r not in _annexes(s2, "SN-0003")]
    assert new == [(held, epoch_us(L3), 0, 0)]
    assert "SN-0003" not in _latest(s3)
    assert _annexes(s4, "SN-0003") == _annexes(s3, "SN-0003")

    for snap in (s3, s5):
        assert _tt(snap, "2014-02-20", posited(L3, -1)).get("SN-0003") == 2, "tPR before L3 lost SN-0003's version"
        assert "SN-0003" not in _tt(snap, "2014-02-20", posited(L3)), "tPR at L3 still shows the retracted version"

    # EC4: restored in L5 at 2014-05-01.
    assert [(v, d) for _, v, d in _posits(s5, "SN-0003")] == [(2, D0), (2, RESTORE)]
    assert _latest(s5)["SN-0003"] == 2
    assert _pit(s5, "2014-05-15")["SN-0003"] == 2
    assert "SN-0003" not in _tt(s5, "2014-05-15", posited(L5, -1)), "tPR before L5 shows the restored version"
    assert _tt(s5, "2014-05-15", posited(L5)).get("SN-0003") == 2
    assert _tt(s5, "2014-05-15", "date '9999-12-31'").get("SN-0003") == 2


# --------------------------------------------------------------------------- AC7


def test_tie_unknown_reference(story):
    """AC7 ([5]): SN-0004 references subcategory 3 before it has landed: after L1 no tie row; after L2,
    once 3 has landed and the row repeats, one posit to 3 at ChangedAt 2014-02-08, posited at L2."""
    s1, s2, s5 = story.snap("L1"), story.snap("L2"), story.snap("L5")
    assert 3 not in source_ids(s1).values(), "subcategory 3 has an identity before it landed"
    assert _posits(s1, "SN-0004") == []
    assert "SN-0004" not in _latest(s1)
    assert [(v, d) for _, v, d in _posits(s2, "SN-0004")] == [(3, D0)]
    assert [(r[1], r[2], r[3]) for r in _annexes(s2, "SN-0004")] == [(epoch_us(L2), 0, 1)]
    assert _latest(s2)["SN-0004"] == 3
    assert _posits(s5, "SN-0004") == _posits(s2, "SN-0004")
    assert _annexes(s5, "SN-0004") == _annexes(s2, "SN-0004")


# --------------------------------------------------------------------------- AC8


def test_tie_contradiction(story):
    """AC8 ([6]): a load with two SN-0001 rows at one ModifiedDate and different subcategories fails dbt build,
    naming the tie and the contradiction, and writes no tie row from that load."""
    story.snap("full")
    snap = story.contradiction
    assert snap is not None, story.contradiction_failure
    assert snap.returncode != 0, f"the contradicting load built:\n{tail(snap.output)}"
    output = snap.output
    assert TIE in output, f"the build failed without naming {TIE}:\n{tail(output)}"
    assert "contradiction" in output.lower() or "two different values for one version" in output, (
        f"the build failed for another reason than the contradiction:\n{tail(output)}"
    )
    before = story.snap("L5")
    for table in (TIE_POSIT, TIE_ANNEX):
        query = f"select * from integrate.{q(table)} order by all"
        assert snap.sql(query) == before.sql(query), f"the contradicting load wrote to {table}"


# --------------------------------------------------------------------------- AC4


def test_tie_test_warns(story):
    """AC4 ([7]): with a duplicate posit written straight into PR_in_PS_contains_Posit, dbt test exits 0
    and reports the tie's key test as a warning; IntegrityViolations still passes."""
    story.snap("full")
    snap = story.duplicate
    assert snap is not None, story.duplicate_failure
    assert snap.returncode == 0, f"dbt test exited {snap.returncode} on a duplicate tie posit:\n{tail(snap.output)}"
    tests = [r for r in snap.results() if r["unique_id"].startswith("test.")]
    tie_tests = [r for r in tests if TIE in r["unique_id"]]
    assert tie_tests, f"no dbt test names {TIE}: {[r['unique_id'] for r in tests]}"
    warned = [r["unique_id"] for r in tie_tests if r["status"] == "warn"]
    assert warned, f"no tie test warned: {[(r['unique_id'], r['status']) for r in tie_tests]}"
    integrity = [r for r in tests if "integrityviolations" in r["unique_id"].lower().replace("_", "")]
    assert integrity, "no IntegrityViolations test ran"
    assert all(r["status"] == "pass" for r in integrity), [(r["unique_id"], r["status"]) for r in integrity]
    nodes = snap.manifest["nodes"]
    for r in warned:
        severity = str(nodes[r]["config"].get("severity", "")).lower()
        assert severity == "warn", f"{r} warned at severity {severity!r}"
