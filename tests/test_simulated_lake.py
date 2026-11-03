"""The simulated lake end to end (story #25, AC7, AC8, EC6).

``uv run simulate --seed 7 --loads 6`` lands the snapshot and six changed Products loads. The
loads reach the workspace's lake one at a time, oldest load id first, with ``dbt build`` after
each: the full seeded lake is simulated into a staging folder and its files are moved across in
load-id order, so the builds see the same rows an empty-lake run writes (AC1).

The answer serve gives is held to ``replay.on_sale``, computed from the lake's rows alone, and the
history every build holds to ``replay.products`` over the loads landed so far (story #4).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

import replay
from harness import (
    ATTRIBUTES,
    PIT,
    REPO,
    RESOURCE,
    TT,
    Snapshot,
    Workspace,
    annex,
    at,
    attribute,
    dimension_column,
    integrity_violations,
    load_id,
    pit,
    pit_columns,
    posit,
    q,
    same_rows,
    tail,
    timestamp,
    tt,
    tt_columns,
    write_load,
)
from test_end_to_end import _attribute_columns, base_products, business_products, load_3, load_4, load_5

SNAPSHOT = REPO / "src" / "simulate" / "adventure_works__products.jsonl"
BUILDS = 7  # the snapshot load, then six changed loads


def _load_id_of(path: Path) -> Decimal:
    import duckdb

    con = duckdb.connect()
    try:
        ids = {r[0] for r in con.execute(f"select distinct _dlt_load_id from read_parquet('{path.as_posix()}')").fetchall()}
    finally:
        con.close()
    assert len(ids) == 1, f"{path} holds load ids {ids}, expected one"
    return Decimal(ids.pop())


class SimulatedLake:
    """The workspace, a snapshot after every build, and the first failure if a step failed."""

    def __init__(self, ws: Workspace):
        self.ws = ws
        self.snaps: list[Snapshot] = []
        self.failure = "it has not run"

    def snap(self, n: int) -> Snapshot:
        if n >= len(self.snaps):
            pytest.fail(f"the simulated lake never reached build {n + 1}: {self.failure}")
        return self.snaps[n]


@pytest.fixture(scope="module")
def simulated(make_workspace) -> SimulatedLake:
    ws = make_workspace("simulated")
    lake = SimulatedLake(ws)
    staging = ws.root.parent / "staging-lake"
    env = ws.env()
    env["LAKE_ROOT"] = str(staging)
    proc = subprocess.run(
        ["uv", "run", "simulate", "--seed", "7", "--loads", "6"],
        cwd=ws.root,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )
    if proc.returncode != 0:
        lake.failure = f"uv run simulate exited {proc.returncode}:\n{tail(proc.stdout + proc.stderr)}"
        return lake
    files = sorted((staging / RESOURCE).rglob("*.parquet"), key=_load_id_of)
    if len(files) != BUILDS:
        lake.failure = f"uv run simulate wrote {len(files)} files, expected {BUILDS}: {files}"
        return lake
    step = ws.generate()
    if step.returncode != 0:
        lake.failure = f"task generate exited {step.returncode}:\n{tail(step.output)}"
        return lake
    for n, source in enumerate(files):
        target = ws.lake / source.relative_to(staging)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(source, target)
        step = ws.build()
        if step.returncode != 0:
            lake.failure = f"dbt build after load {n} exited {step.returncode}:\n{tail(step.output)}"
            return lake
        lake.snaps.append(ws.snapshot(f"build-{n}", step))
    return lake


# --------------------------------------------------------------------------- AC7


def test_every_build_passes(simulated):
    """AC7: seed 7, 6 loads, one load at a time: every build exits 0, every dbt test passes and
    IntegrityViolations is empty."""
    for n in range(BUILDS):
        snap = simulated.snap(n)
        tests = [r for r in snap.results() if r["unique_id"].startswith("test.")]
        assert tests, f"build {n + 1} ran no dbt test"
        bad = [(r["unique_id"], r["status"]) for r in tests if r["status"] not in ("pass", "warn")]
        assert not bad, f"build {n + 1}: {bad}"
        failed = [(r["unique_id"], r["status"]) for r in snap.results() if r["status"] in ("error", "fail")]
        assert not failed, f"build {n + 1}: {failed}"
        assert integrity_violations(snap) == 0, f"build {n + 1}"
    last = simulated.snap(BUILDS - 1)
    assert last.count("conform", last.staged()) > 504 * 6, "conform does not hold every simulated load"


# --------------------------------------------------------------------------- AC8


def _serve_on_sale(snap: Snapshot, day: str) -> list[tuple]:
    """#1's business question (test_business_question's serve query) on ``day``."""
    line, color = dimension_column(snap, "line"), dimension_column(snap, "color")
    start, end, disc = (dimension_column(snap, w) for w in ("sell_start", "sell_end", "discontinued"))
    d = f"date '{day}'"
    rows = snap.sql(
        f"select {q(line)}, {q(color)}, count(*) from serve__uss.product "
        "where _key__product like '%|%' "
        f"and cast(product__valid_from as date) <= {d} and {d} < cast(product__valid_to as date) "
        f"and cast({q(start)} as date) <= {d} "
        f"and ({q(end)} is null or cast({q(end)} as date) >= {d}) "
        f"and ({q(disc)} is null or {d} < cast({q(disc)} as date)) "
        "group by all"
    )
    return sorted(rows, key=repr)


def _earliest_sell_start() -> str:
    starts = [
        json.loads(line).get("SellStartDate")
        for line in SNAPSHOT.read_text().splitlines()
        if line.strip()
    ]
    return min(str(s)[:10] for s in starts if s)


def test_business_answer_matches_replay(simulated):
    """AC8, EC5: after the last build, serve's count of products on sale per product line and colour
    equals the independent answer on 2014-02-09, 2014-02-12, 2014-02-15 and the earliest sell start."""
    snap = simulated.snap(BUILDS - 1)
    days = ["2014-02-09", "2014-02-12", "2014-02-15", _earliest_sell_start()]
    answered = {}
    for day in days:
        expected = replay.on_sale(simulated.ws.lake, day)
        assert _serve_on_sale(snap, day) == expected, day
        answered[day] = expected
    assert any(answered.values()), f"no product is on sale on any of {days}: the check proves nothing"


# --------------------------------------------------------------------------- EC6


def test_replay_matches_story1(tmp_path):
    """EC6: the independent answer over #1's business lake gives #1's answer for 2013-06-01, no dbt."""
    lake = tmp_path / "lake"
    write_load(lake, load_id(1), business_products())
    assert replay.on_sale(lake, "2013-06-01") == sorted(
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


def test_replay_applies_the_rules_to_story1_lake(tmp_path):
    """EC6: over #1's main story lake (loads 1 to 5) the replay holds what #1's tests prove integrate
    holds: a new value, a correction, a source null, a failed cast, A-B-A, absence, a new product."""
    lake = tmp_path / "lake"
    for n, rows in enumerate(
        (base_products(), base_products(), load_3(), load_4(), load_5()), start=1
    ):
        write_load(lake, load_id(n), list(rows.values()))
    held = replay.products(lake)
    today, before = date(2014, 6, 1), date(2014, 2, 1)

    def on(number: str, field: str, day: date = today):
        return held[number][field].on(day)

    assert on("SC-0001", "Color") == "Red"
    assert on("SC-0001", "Color", date(2014, 2, 28)) == "Black"
    assert on("SC-0001", "ProductLine") == "R"
    assert on("SN-0002", "Name") == "Alpha Prime"
    assert on("SN-0002", "Name", before) == "Alpha Prime"
    assert on("SE-0003", "SellEndDate") is None
    assert on("SX-0005", "SellStartDate") == date(2011, 5, 31)
    assert on("SB-0007", "Color") == "Blue"
    assert on("SB-0007", "Color", date(2014, 3, 15)) == "Yellow"
    assert on("SA-0006", "Color") == "Blue"
    assert on("SA-0006", "Color", date(2014, 3, 15)) == "Yellow"
    assert on("SG-0004", "Name") == "Gone Bike"
    assert on("SN-0009", "Name") == "Newcomer"
    assert on("SS-0008", "DiscontinuedDate") == date(2015, 1, 1)
    assert set(held) == {f"S{c}-000{i}" for c, i in zip("CNEGXABSN", range(1, 10))}


# --------------------------------------------------------------------------- story #4: history in every layer

# The contract's field each mnemonic loads, and the dimension column serve casts it into.
FIELDS = {
    "NUM": ("ProductNumber", "number"),
    "NAM": ("Name", "name"),
    "LIN": ("ProductLine", "line"),
    "COL": ("Color", "color"),
    "SST": ("SellStartDate", "sell_start"),
    "SEN": ("SellEndDate", "sell_end"),
    "DIS": ("DiscontinuedDate", "discontinued"),
}
DATE_MNEMONICS = ("SST", "SEN", "DIS")
FIRST_VERSION = datetime(1, 1, 1)


def _moment(value) -> datetime:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo is None else value.astimezone(UTC).replace(tzinfo=None)
    return datetime(value.year, value.month, value.day)


def _text(mnemonic: str, value):
    if value is None:
        return None
    return str(value)[:10] if mnemonic in DATE_MNEMONICS else str(value)


def _numbers(snap: Snapshot) -> dict:
    """PR_ID -> ProductNumber, from the ProductNumber posits."""
    m = "NUM"
    pairs = snap.sql(f"select distinct PR_{m}_PR_ID, {q(attribute(m))} from integrate.{q(posit(m))}")
    numbers = dict(pairs)
    assert len(numbers) == len(pairs), "a PR_ID holds two ProductNumbers"
    assert len(set(numbers.values())) == len(numbers), "a ProductNumber has two PR_IDs"
    return numbers


def _reliable_posits(snap: Snapshot) -> dict:
    """PR_ID -> mnemonic -> [(ChangedAt, value as text)] of integrate's reliable positor-0 posits:
    those whose latest positor-0 annex row, by PositedAt, has Reliability 1."""
    held: dict = defaultdict(lambda: defaultdict(list))
    for m in ATTRIBUTES:
        rows = snap.sql(
            f"select p.PR_{m}_PR_ID, p.PR_{m}_ChangedAt, p.{q(attribute(m))} "
            f"from integrate.{q(posit(m))} p join ("
            f"  select PR_{m}_ID, PR_{m}_Reliability, "
            f"  row_number() over (partition by PR_{m}_ID order by PR_{m}_PositedAt desc) as newest "
            f"  from integrate.{q(annex(m))} where PR_{m}_Positor = 0"
            f") a on a.PR_{m}_ID = p.PR_{m}_ID and a.newest = 1 "
            f"where a.PR_{m}_Reliability = 1"
        )
        for identity, changed_at, value in rows:
            held[identity][m].append((_moment(changed_at), _text(m, value)))
    for attributes in held.values():
        for posits_ in attributes.values():
            posits_.sort()
    return held


def _dimension(snap: Snapshot) -> dict:
    """PR_ID as text -> [(valid_from, valid_to, {mnemonic: value as text})] in valid-from order."""
    columns = {m: dimension_column(snap, what) for m, (_, what) in FIELDS.items()}
    mnemonics = list(columns)
    rows = snap.sql(
        "select split_part(_key__product, '|', 1), product__valid_from, product__valid_to, "
        + ", ".join(q(columns[m]) for m in mnemonics)
        + " from serve__uss.product where _key__product like '%|%' order by 1, 2"
    )
    versions: dict = defaultdict(list)
    for identity, valid_from, valid_to, *values in rows:
        versions[identity].append(
            (_moment(valid_from), _moment(valid_to), {m: _text(m, v) for m, v in zip(mnemonics, values)})
        )
    return versions


def _lake_through(lake: Path, files: list[Path], target: Path) -> Path:
    """A copy of ``lake`` holding only ``files``: the loads a build had seen."""
    for source in files:
        copy = target / source.relative_to(lake)
        copy.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, copy)
    return target


def test_history_matches_replay(simulated, tmp_path):
    """AC5: at every one of the 7 builds, each product's reliable posits per attribute (ChangedAt, value)
    equal the replay's over the loads landed so far, and the dimension's valid-froms per product equal
    the union of the replay's reliable ChangedAts, each attribute's first moved to 0001-01-01."""
    landed = sorted((simulated.ws.lake / RESOURCE).rglob("*.parquet"), key=_load_id_of)
    assert len(landed) == BUILDS, landed
    for n in range(BUILDS):
        snap = simulated.snap(n)
        lake = _lake_through(simulated.ws.lake, landed[: n + 1], tmp_path / f"build-{n}")
        expected = replay.products(lake)
        numbers = _numbers(snap)
        held = _reliable_posits(snap)
        versions = _dimension(snap)
        assert sorted(numbers.values()) == sorted(expected), f"build {n + 1}: products differ from the replay's"
        wrong = []
        for identity, number in sorted(numbers.items(), key=lambda item: item[1]):
            changed_ats = set()
            for m, (field, _) in FIELDS.items():
                want = [(_moment(c), _text(m, v)) for c, v in expected[number][field].reliable()]
                got = held[identity][m]
                if got != want:
                    wrong.append(f"{number} {attribute(m)}: integrate {got}, replay {want}")
                # Serve backfills each attribute's first value, not only the product's earliest, so an
                # attribute first posited later than the others starts no version of its own.
                changed_ats |= {FIRST_VERSION, *(c for c, _ in want[1:])} if want else set()
            want_from = sorted(changed_ats)
            got_from = [v[0] for v in versions[str(identity)]]
            if got_from != want_from:
                wrong.append(f"{number} valid-froms: dimension {got_from}, replay {want_from}")
        assert not wrong, f"build {n + 1}, {len(wrong)} disagreements:\n" + "\n".join(wrong[:20])


def test_pit_shape_every_simulated_build(simulated):
    """AC1: after every simulated build, pPR_Product runs and returns lPR_Product's column names, in order."""
    for n in range(BUILDS):
        snap = simulated.snap(n)
        when = at("2014-02-10 00:00:00")
        assert pit_columns(snap, when) == snap.columns("integrate", "lPR_Product"), f"build {n + 1}"
        snap.sql(f"select count(*) from {PIT}({when})")


def test_pit_matches_dimension(simulated):
    """AC6, EC6: after the last build, at every probe time (each valid-from, one second before each
    valid-to, 2013-06-01, 2099-01-01), for every product and attribute, pPR's value equals the dimension
    version valid then from the attribute's first reliable ChangedAt on, and is null before it."""
    snap = simulated.snap(BUILDS - 1)
    versions = _dimension(snap)
    held = _reliable_posits(snap)
    first = {(str(identity), m): posits_[0][0] for identity, ms in held.items() for m, posits_ in ms.items() if posits_}
    probes = {datetime(2013, 6, 1), datetime(2099, 1, 1)}
    for vs in versions.values():
        for valid_from, valid_to, _ in vs:
            probes |= {valid_from, valid_to - timedelta(seconds=1)}

    wrong, compared, unbackfilled = [], 0, 0
    for probe in sorted(probes):
        rows = pit(snap, at(probe.isoformat(sep=" ", timespec="seconds")))
        rows = {str(identity): record for identity, record in rows.items()}
        assert set(rows) == set(versions), f"pPR({probe}) returns other identities than the dimension holds"
        for identity, vs in versions.items():
            valid = [v for f, t, v in vs if f <= probe < t]
            assert len(valid) == 1, f"{identity} has {len(valid)} dimension versions valid at {probe}"
            for m in FIELDS:
                got = _text(m, rows[identity][attribute(m)])
                since = first.get((identity, m))
                if since is None or probe < since:
                    want = None
                    unbackfilled += valid[0][m] is not None
                else:
                    want = valid[0][m]
                    compared += 1
                if got != want:
                    wrong.append(f"pPR({probe}) PR_ID {identity} {attribute(m)}: {got!r}, expected {want!r}")
    assert not wrong, f"{len(wrong)} mismatches:\n" + "\n".join(wrong[:20])
    assert compared > 1000, f"only {compared} values compared: the check proves little"
    assert unbackfilled > 0, "no probe fell before a first ChangedAt where serve backfills: [2] is not exercised"

    latest_rows, point = "select * from integrate.lPR_Product", f"select * from {PIT}({at('2099-01-01')})"
    for one, other in ((latest_rows, point), (point, latest_rows)):
        assert snap.sql(f"select count(*) from ({one} except all {other})") == [(0,)], f"`{one}` has rows `{other}` lacks"


# --------------------------------------------------------------------------- story #5: tPR_Product


def _latest_posited(snap: Snapshot) -> datetime:
    """The latest ``_dlt__extracted_at`` conform holds: the PositedAt of the last load ``snap``'s build had seen."""
    (latest,) = snap.sql(f"select max(_dlt__extracted_at) from conform.{q(snap.staged())}")[0]
    return _moment(latest)


def _tt_probes(snap: Snapshot) -> set[datetime]:
    """Each dimension valid-from, 2013-06-01 and 2099-01-01."""
    probes = {datetime(2013, 6, 1), datetime(2099, 1, 1)}
    for vs in _dimension(snap).values():
        probes |= {valid_from for valid_from, _, _ in vs}
    return probes


def test_tt_equals_pit_simulated(simulated):
    """Story #5 AC4, EC4: after the last build, tPR(T, K) with K at or after the latest load's PositedAt
    equals pPR(T) row for row, for T at each dimension valid-from, 2013-06-01 and 2099-01-01; before an
    attribute's first ChangedAt it shows no value, as pPR does."""
    snap = simulated.snap(BUILDS - 1)
    last_load = timestamp(_latest_posited(snap))
    probes = _tt_probes(snap)

    wrong = []
    for probe in sorted(probes):
        when = at(probe.isoformat(sep=" ", timespec="seconds"))
        point = f"select * from {PIT}({when})"
        for positing in ("date '9999-12-31'", last_load):
            wrong += same_rows(snap, f"select * from {TT}({when}, {positing})", point)
    assert not wrong, f"{len(wrong)} mismatches:\n" + "\n".join(wrong[:20])

    held = _reliable_posits(snap)
    first = {(identity, m): posits_[0][0] for identity, ms in held.items() for m, posits_ in ms.items() if posits_}
    unknown_yet = 0
    for probe in sorted(probes):
        rows = tt(snap, at(probe.isoformat(sep=" ", timespec="seconds")), "date '9999-12-31'")
        for (identity, m), since in first.items():
            if probe < since:
                unknown_yet += 1
                value = rows[identity][attribute(m)]
                assert value is None, f"tPR({probe}, late K) PR_ID {identity} {attribute(m)} is {value!r} before {since}"
    assert unknown_yet > 0, "no probe fell before an attribute's first ChangedAt: EC4 is not exercised"


def _source_null_retractions(lake: Path, landed: list[Path], tmp_path: Path) -> list[str]:
    """The replay's source-null retractions of a version that had an earlier reliable one, by a load before
    the last: a load that turned a reliable posit unreliable and made none reliable, leaving one with an
    earlier ChangedAt."""
    found = []
    before = replay.products(_lake_through(lake, landed[:1], tmp_path / "through-0"))
    for n in range(1, len(landed) - 1):
        after = replay.products(_lake_through(lake, landed[: n + 1], tmp_path / f"through-{n}"))
        for number, fields in after.items():
            for field, held in fields.items():
                was = set(before[number][field].reliable()) if number in before else set()
                now = set(held.reliable())
                if now - was or not was - now:
                    continue
                for retracted, _ in was - now:
                    if any(c < retracted for c, _ in now):
                        found.append(f"load {n + 1}: {number} {field} at {retracted}")
        before = after
    return found


def test_tt_known_at_each_build(simulated, tmp_path):
    """Story #5 AC10, AC3: after the last build, tPR(T, K_i), with K_i the PositedAt of the last load build i
    had seen, equals build i's pPR(T) row for row, for every build i and the T's test_tt_equals_pit_simulated
    uses. Identities first posited after K_i are the only extra rows, every attribute null (EC1). The lake
    holds a source null that lets an earlier version show again, before the last load."""
    landed = sorted((simulated.ws.lake / RESOURCE).rglob("*.parquet"), key=_load_id_of)
    assert len(landed) == BUILDS, landed
    retractions = _source_null_retractions(simulated.ws.lake, landed, tmp_path)
    assert retractions, "no load before the last retracts a version with an earlier one: AC3's 'if any' is not exercised"

    last = simulated.snap(BUILDS - 1)
    probes = sorted(_tt_probes(last))
    wrong, compared = [], 0
    for n in range(BUILDS):
        then = simulated.snap(n)
        known_at = timestamp(_latest_posited(then))
        held_then = {r[0] for r in then.sql("select PR_ID from integrate.PR_Product")}
        for probe in probes:
            when = timestamp(probe)
            columns = tt_columns(last, when, known_at)
            assert columns == pit_columns(then, when), f"build {n + 1}: tPR's columns differ from pPR's then"
            known = tt(last, when, known_at)
            later = [r for pid, r in known.items() if pid not in held_then]
            valued = [(r["PR_ID"], c) for r in later for c in _attribute_columns(columns) if r[c] is not None]
            if valued:
                wrong.append(f"build {n + 1}, T {probe}: identities posited after K hold values: {valued[:5]}")
            got = Counter(tuple(r.values()) for pid, r in known.items() if pid in held_then)
            want = Counter(tuple(r.values()) for r in pit(then, when).values())
            compared += sum(want.values())
            if got != want:
                missing, extra = want - got, got - want
                wrong.append(
                    f"build {n + 1}, T {probe}: tPR at the last build lacks {sum(missing.values())} of pPR's rows "
                    f"then and has {sum(extra.values())} more, e.g. lacks {list(missing)[:1]}, has {list(extra)[:1]}"
                )
    assert not wrong, f"{len(wrong)} mismatches:\n" + "\n".join(wrong[:20])
    assert compared > 1000, f"only {compared} rows compared: the check proves little"
