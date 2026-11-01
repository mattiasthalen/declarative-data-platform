"""The simulated lake end to end (story #25, AC7, AC8, EC6).

``uv run simulate --seed 7 --loads 6`` lands the snapshot and six changed Products loads. The
loads reach the workspace's lake one at a time, oldest load id first, with ``dbt build`` after
each: the full seeded lake is simulated into a staging folder and its files are moved across in
load-id order, so the builds see the same rows an empty-lake run writes (AC1).

The answer serve gives is held to ``replay.on_sale``, computed from the lake's rows alone.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

import replay
from harness import (
    REPO,
    RESOURCE,
    Snapshot,
    Workspace,
    dimension_column,
    integrity_violations,
    load_id,
    q,
    tail,
    write_load,
)
from test_end_to_end import base_products, business_products, load_3, load_4, load_5

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
