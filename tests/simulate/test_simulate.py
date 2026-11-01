"""The seeded change simulator (story #25).

The seam these tests call: ``simulate.main(argv) -> int``, the ``uv run simulate`` entry point,
with ``LAKE_ROOT`` naming the lake. It appends Products loads in the layout ``harness.write_load``
writes: ``$LAKE_ROOT/adventure_works__products/date=YYYY-MM-DD/hour=HH/<load_id>.<file_id>.parquet``
with the columns ``data`` (the row as JSON text), ``_dlt_load_id`` and ``_dlt_id``. On an empty
lake the first load is the committed snapshot ``src/simulate/adventure_works__products.jsonl``
at 2014-02-09T00:00:00Z, and each changed load follows a day later.

The lake is read back with DuckDB, and the change kinds are told apart from the diff of each
load against the one before, never from the simulator's own records.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import socket
import subprocess
import time
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from harness import REPO, RESOURCE, load_id, product, write_load

SNAPSHOT = REPO / "src" / "simulate" / "adventure_works__products.jsonl"
FIRST_LOAD = datetime(2014, 2, 9, tzinfo=UTC)
BUSINESS = ("Name", "ProductLine", "Color", "SellStartDate", "SellEndDate", "DiscontinuedDate")
LANDED = {"data", "_dlt_load_id", "_dlt_id"}
KINDS = ("edit", "correction", "source null", "late arrival", "new product", "drop out")


# --------------------------------------------------------------------------- running it


def run(monkeypatch, capsys, lake: Path, *argv: str) -> tuple[int, str, str]:
    """Run ``simulate.main(argv)`` against ``lake``; return (exit code, stdout, stderr)."""
    import simulate

    monkeypatch.setenv("LAKE_ROOT", str(lake))
    capsys.readouterr()
    try:
        code = simulate.main(list(argv))
    except SystemExit as exit_:
        code = exit_.code if isinstance(exit_.code, int) else (0 if exit_.code is None else 2)
    out, err = capsys.readouterr()
    return code, out, err


# --------------------------------------------------------------------------- reading the lake


def files(lake: Path) -> list[Path]:
    return sorted((lake / RESOURCE).rglob("*.parquet")) if (lake / RESOURCE).exists() else []


def every_file(lake: Path) -> list[Path]:
    return sorted(p for p in lake.rglob("*") if p.is_file()) if lake.exists() else []


def hashes(lake: Path) -> dict[str, str]:
    return {p.relative_to(lake).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in every_file(lake)}


def read_file(path: Path) -> tuple[list[str], list[tuple[str, str, str]]]:
    """(column names, rows of (data, _dlt_load_id, _dlt_id)) of one landed file."""
    import duckdb

    con = duckdb.connect()
    try:
        relation = f"read_parquet('{path.as_posix()}', hive_partitioning = false)"
        columns = [r[0] for r in con.execute(f"describe select * from {relation}").fetchall()]
        rows = con.execute(
            f"select cast(data as varchar), cast(_dlt_load_id as varchar), cast(_dlt_id as varchar) from {relation}"
        ).fetchall()
    finally:
        con.close()
    return columns, rows


class Load:
    """One landed file: its load id, its rows, and its rows by ProductNumber."""

    def __init__(self, path: Path):
        self.path = path
        self.columns, raw = read_file(path)
        ids = {r[1] for r in raw}
        assert len(ids) == 1, f"{path} holds load ids {ids}, expected exactly one"
        self.load_id = ids.pop()
        self.raw = raw
        self.rows = [json.loads(r[0]) for r in raw]

    @property
    def number(self) -> Decimal:
        return Decimal(self.load_id)

    @property
    def landed(self) -> datetime:
        return datetime.fromtimestamp(float(self.load_id), UTC)

    @property
    def day(self) -> date:
        return self.landed.date()

    def by_number(self) -> dict[str, dict]:
        return {row["ProductNumber"]: row for row in self.rows}

    def triples(self) -> set[tuple[str, str, str]]:
        """(load id, _dlt_id, data as canonical JSON) of every row."""
        return {(r[1], r[2], json.dumps(json.loads(r[0]), sort_keys=True)) for r in self.raw}


def loads(lake: Path) -> list[Load]:
    """Every Products load in the lake, in load-id order."""
    return sorted((Load(p) for p in files(lake)), key=lambda load: load.number)


def assert_landed_shape(load: Load) -> None:
    assert set(load.columns) == LANDED, f"{load.path.name} has columns {load.columns}"
    landed = load.landed
    assert load.path.parent.name == f"hour={landed:%H}", load.path
    assert load.path.parent.parent.name == f"date={landed:%Y-%m-%d}", load.path
    assert load.path.parent.parent.parent.name == RESOURCE, load.path
    assert load.path.name.startswith(load.load_id + "."), (load.path.name, load.load_id)
    assert load.path.name.endswith(".parquet"), load.path.name
    for data, _, dlt_id in load.raw:
        assert isinstance(json.loads(data), dict), data
        assert dlt_id, f"{load.path.name}: a row without a _dlt_id"


def snapshot_rows() -> list[dict]:
    return [json.loads(line) for line in SNAPSHOT.read_text().splitlines() if line.strip()]


def canonical(rows: list[dict]) -> Counter:
    return Counter(json.dumps(row, sort_keys=True) for row in rows)


def modified(row: dict) -> date | None:
    value = row.get("ModifiedDate")
    return None if value is None else date.fromisoformat(str(value)[:10])


# --------------------------------------------------------------------------- the diff


def diff(history: list[Load]) -> list[dict]:
    """Each changed load (1..n) against the load before, classified from the rows alone.

    Per load: ``changed`` (number -> (before, after, kind)) for products in both loads, or back
    from a drop with a change; ``new`` (number -> row); ``dropped`` (numbers); ``returned``
    (numbers back unchanged); ``kinds`` (a Counter of every change's kind).
    """
    out = []
    seen_numbers = {row["ProductNumber"] for row in history[0].rows}
    seen_ids = {row["ProductId"] for row in history[0].rows}
    last_seen = dict(history[0].by_number())
    for before_load, load in zip(history, history[1:]):
        before, after = before_load.by_number(), load.by_number()
        found = {"load": load, "changed": {}, "new": {}, "dropped": set(), "returned": set(), "kinds": Counter()}
        for number in before.keys() - after.keys():
            found["dropped"].add(number)
            found["kinds"]["drop out"] += 1
        for number, row in after.items():
            if number in before:
                previous = before[number]
            elif number in last_seen:
                previous = last_seen[number]
                if row == previous:
                    found["returned"].add(number)
                    continue
            else:
                found["new"][number] = row
                found["kinds"]["new product"] += 1
                continue
            if row == previous:
                continue
            kind = classify(previous, row, load.day)
            found["changed"][number] = (previous, row, kind)
            found["kinds"][kind] += 1
        found["seen_numbers"], found["seen_ids"] = set(seen_numbers), set(seen_ids)
        seen_numbers |= after.keys()
        seen_ids |= {row["ProductId"] for row in load.rows}
        last_seen.update(after)
        out.append(found)
    return out


def classify(before: dict, after: dict, day: date) -> str:
    """The kind of one product's change, from its row before and after; ``unknown`` if none fits."""
    attributes = [k for k in BUSINESS if before.get(k) != after.get(k)]
    if not attributes:
        return "unknown"
    was, now = modified(before), modified(after)
    nulled = any(before.get(k) is not None and after.get(k) is None for k in attributes)
    if now == day and was != day:
        return "source null" if nulled else "edit"
    if now == was:
        return "correction"
    if was is not None and now == was - timedelta(days=1):
        return "late arrival"
    return "unknown"


@pytest.fixture(scope="module")
def seven(tmp_path_factory):
    """The lake of ``simulate --seed 7 --loads 6`` on an empty lake, and its exit code, or what it
    raised: each test that reads it then fails on its own."""
    lake = tmp_path_factory.mktemp("seven") / "lake"
    lake.mkdir()
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("LAKE_ROOT", str(lake))
        try:
            import simulate

            code = simulate.main(["--seed", "7", "--loads", "6"])
        except SystemExit as exit_:
            code = exit_.code
        except Exception as error:  # noqa: BLE001
            code = repr(error)
    return lake, code


# --------------------------------------------------------------------------- AC1


def test_empty_lake_lands_snapshot_then_loads(monkeypatch, capsys, tmp_path):
    """AC1: an empty lake, seed 7, 6 loads: 7 files in the landed shape, the snapshot first, load ids
    2014-02-09T00:00:00Z plus 0..6 days as fractional epoch seconds; exit 0."""
    lake = tmp_path / "lake"
    lake.mkdir()
    code, out, err = run(monkeypatch, capsys, lake, "--seed", "7", "--loads", "6")
    assert code == 0, err
    paths = files(lake)
    assert len(paths) == 7, paths
    assert len(every_file(lake)) == 7, every_file(lake)
    history = loads(lake)
    assert len({load.load_id for load in history}) == 7, [load.load_id for load in history]
    for k, load in enumerate(history):
        assert_landed_shape(load)
        assert re.fullmatch(r"\d+\.\d+", load.load_id), load.load_id
        assert Decimal(load.load_id) == Decimal(int(FIRST_LOAD.timestamp()) + 86400 * k), (k, load.load_id)
    first = history[0]
    assert len(first.rows) == 504
    snapshot = snapshot_rows()
    assert len(snapshot) == 504, "the committed snapshot does not hold 504 rows"
    assert canonical(first.rows) == canonical(snapshot)


# --------------------------------------------------------------------------- AC2


def _per_load(lake: Path) -> list[set]:
    return [load.triples() for load in loads(lake)]


def test_same_seed_same_rows(monkeypatch, capsys, tmp_path):
    """AC2: two empty-lake runs with seed 7 give the same (load id, _dlt_id, data) per load; seed 8 differs."""
    results = {}
    for label, seed in (("a", "7"), ("b", "7"), ("c", "8")):
        lake = tmp_path / label
        lake.mkdir()
        code, _, err = run(monkeypatch, capsys, lake, "--seed", seed, "--loads", "6")
        assert code == 0, err
        results[label] = _per_load(lake)
    assert len(results["a"]) == 7
    assert results["a"] == results["b"]
    assert results["a"] != results["c"]


# --------------------------------------------------------------------------- AC3, EC8


def test_change_kinds(seven):
    """AC3, EC8: across seed 7's loads every kind occurs, each load changes 3% to 7% of the products
    before it, one row per ProductNumber, and only the six attributes and ModifiedDate change."""
    lake, code = seven
    assert code == 0, f"simulate --seed 7 --loads 6 ended with {code}"
    history = loads(lake)
    assert len(history) == 7
    keys = set(history[0].rows[0])
    for load in history:
        numbers = Counter(row["ProductNumber"] for row in load.rows)
        twice = [n for n, c in numbers.items() if c > 1]
        assert not twice, f"load {load.load_id} holds two rows for {twice}"
        for row in load.rows:
            assert set(row) == keys, f"load {load.load_id}: {row.get('ProductNumber')} has keys {set(row) ^ keys}"
    total = Counter()
    for before, found in zip(history, diff(history)):
        changes = len(found["changed"]) + len(found["new"]) + len(found["dropped"])
        share = changes / len(before.rows)
        assert 0.03 <= share <= 0.07, f"load {found['load'].load_id} changed {changes} of {len(before.rows)}"
        for number, (previous, row, kind) in found["changed"].items():
            moved = {k for k in row if row.get(k) != previous.get(k)}
            assert moved <= set(BUSINESS) | {"ModifiedDate"}, f"{number} changed {moved}"
            assert kind != "unknown", f"{number} changed in no known way: {previous} -> {row}"
        total += found["kinds"]
    missing = [kind for kind in KINDS if not total[kind]]
    assert not missing, f"seed 7 never made a {missing}; it made {dict(total)}"


# --------------------------------------------------------------------------- AC4


def test_kind_shapes(seven):
    """AC4: each kind has its shape, read from the diff alone."""
    lake, code = seven
    assert code == 0, f"simulate --seed 7 --loads 6 ended with {code}"
    history = loads(lake)
    found_all = diff(history)
    for n, found in enumerate(found_all):
        load = found["load"]
        for number, (previous, row, kind) in found["changed"].items():
            was, now = modified(previous), modified(row)
            if kind in ("edit", "source null"):
                assert now == load.day, (number, kind, row["ModifiedDate"])
            elif kind == "correction":
                assert now == was, (number, kind)
            elif kind == "late arrival":
                assert now == was - timedelta(days=1), (number, kind)
            else:
                pytest.fail(f"{number} in load {load.load_id}: ModifiedDate {was} -> {now} fits no kind")
            if kind == "source null":
                nulled = [k for k in BUSINESS if previous.get(k) is not None and row.get(k) is None]
                assert nulled, (number, previous, row)
        for number, row in found["new"].items():
            assert number not in found["seen_numbers"], number
            assert row["ProductId"] not in found["seen_ids"], (number, row["ProductId"])
            assert row["Name"] not in {r["Name"] for r in history[n].rows}, (number, row["Name"])
        if n + 1 < len(found_all):
            following = history[n + 2].by_number()
            back = [number for number in found["dropped"] if number not in following]
            assert not back, f"dropped in load {load.load_id} and not back in the next: {back}"


# --------------------------------------------------------------------------- AC5


def _hand_written_lake(lake: Path) -> tuple[list[dict], list[dict]]:
    """Two Products loads an hour apart; the later one is a different set of products."""
    older = [product(1000 + i, f"OL-{i:04d}", f"Older {i}") for i in range(50)]
    newer = [
        product(
            2000 + i,
            f"NW-{i:04d}",
            f"Newer {i}",
            color=("Black", "Red", "Silver", None)[i % 4],
            line=("R ", "M ", "T ", None)[i % 4],
        )
        for i in range(200)
    ]
    write_load(lake, load_id(1), older)
    write_load(lake, load_id(2), newer)
    return older, newer


def test_live_lake_appends_after_latest(monkeypatch, capsys, tmp_path):
    """AC5: on a lake with Products loads, 2 new files after the latest load id, within a minute of now;
    they start from the latest load; edits carry the load's UTC date; old files byte for byte unchanged."""
    lake = tmp_path / "lake"
    older, newer = _hand_written_lake(lake)
    before = hashes(lake)
    existing = loads(lake)
    started = time.time()
    code, _, err = run(monkeypatch, capsys, lake, "--seed", "7", "--loads", "2")
    finished = time.time()
    assert code == 0, err
    after = hashes(lake)
    assert {k: after.get(k) for k in before} == before, "an existing file changed or went"
    new_paths = sorted(set(after) - set(before))
    assert len(new_paths) == 2, new_paths
    added = [load for load in loads(lake) if load.load_id not in {e.load_id for e in existing}]
    assert len(added) == 2, [load.load_id for load in added]
    for load in added:
        assert_landed_shape(load)
        assert load.number > max(e.number for e in existing), load.load_id
        assert started - 60 <= float(load.load_id) <= finished + 60, load.load_id
    assert added[0].number < added[1].number

    newer_numbers = {row["ProductNumber"] for row in newer}
    older_numbers = {row["ProductNumber"] for row in older}
    first = added[0].by_number()
    assert not first.keys() & older_numbers, "the new load starts from the older load"
    assert len(first.keys() & newer_numbers) >= 0.9 * len(newer_numbers), "the new load does not start from the latest"

    edits = 0
    for found in diff(existing[1:] + added):
        for number, (previous, row, _) in found["changed"].items():
            now, was = modified(row), modified(previous)
            if now != was and now > was:
                assert now == found["load"].day, (number, row["ModifiedDate"], found["load"].day)
                edits += 1
    assert edits, "two loads of 200 products made no edit"
    for load in added:
        assert abs((load.day - datetime.now(UTC).date()).days) <= 1


# --------------------------------------------------------------------------- AC6


def _seed(out: str, err: str) -> int:
    match = re.search(r"\bseed (\d+)\b", out + "\n" + err)
    assert match, f"no `seed <n>` printed:\n{out}\n{err}"
    return int(match.group(1))


def test_seed_printed_and_replayable(monkeypatch, capsys, tmp_path):
    """AC6: every run prints `seed <n>`; without --seed the seed is random, and rerunning with the
    printed seed on the same starting lake gives the same rows."""
    start = tmp_path / "start"
    _hand_written_lake(start)
    copies = {}
    for label in ("random", "replayed", "other"):
        copies[label] = tmp_path / label
        shutil.copytree(start, copies[label])
    existing = {load.load_id for load in loads(start)}

    code, out, err = run(monkeypatch, capsys, copies["random"], "--loads", "2")
    assert code == 0, err
    seed = _seed(out, err)
    code, out, err = run(monkeypatch, capsys, copies["replayed"], "--seed", str(seed), "--loads", "2")
    assert code == 0, err
    assert _seed(out, err) == seed
    code, out, err = run(monkeypatch, capsys, copies["other"], "--loads", "2")
    assert code == 0, err
    assert _seed(out, err) != seed, "two runs without --seed used the same seed"

    def new_rows(lake: Path) -> list[set]:
        return [{t[1:] for t in load.triples()} for load in loads(lake) if load.load_id not in existing]

    replayed = new_rows(copies["replayed"])
    assert len(replayed) == 2
    assert new_rows(copies["random"]) == replayed

    lake = tmp_path / "empty"
    code, out, err = run(monkeypatch, capsys, lake, "--seed", "7", "--loads", "1")
    assert code == 0, err
    assert _seed(out, err) == 7


# --------------------------------------------------------------------------- AC9


def test_cli_surface():
    """AC9: `task --list` names a simulate task; `uv run simulate --help` names --seed and --loads."""
    listed = subprocess.run(["uv", "run", "task", "--list"], cwd=REPO, capture_output=True, text=True, timeout=300)
    assert listed.returncode == 0, listed.stdout + listed.stderr
    assert re.search(r"^\*\s+simulate:", listed.stdout, re.MULTILINE), listed.stdout
    helped = subprocess.run(
        ["uv", "run", "simulate", "--help"], cwd=REPO, capture_output=True, text=True, timeout=300
    )
    assert helped.returncode == 0, helped.stdout + helped.stderr
    assert "--seed" in helped.stdout and "--loads" in helped.stdout, helped.stdout


# --------------------------------------------------------------------------- AC14


def test_no_network(monkeypatch, capsys, tmp_path):
    """AC14: with outbound connections refused, an empty-lake run and a live-lake run both succeed."""

    def refuse(*args, **kwargs):
        raise OSError("network refused by test_no_network")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)

    empty = tmp_path / "empty"
    code, _, err = run(monkeypatch, capsys, empty, "--seed", "7", "--loads", "2")
    assert code == 0, err
    assert len(files(empty)) == 3

    live = tmp_path / "live"
    _hand_written_lake(live)
    code, _, err = run(monkeypatch, capsys, live, "--seed", "7", "--loads", "1")
    assert code == 0, err
    assert len(files(live)) == 3


# --------------------------------------------------------------------------- EC1


def test_missing_lake_root(monkeypatch, capsys, tmp_path):
    """EC1: a LAKE_ROOT that does not exist is an empty lake: created, snapshot plus K loads, exit 0."""
    lake = tmp_path / "not" / "there"
    code, _, err = run(monkeypatch, capsys, lake, "--seed", "7", "--loads", "2")
    assert code == 0, err
    assert lake.is_dir()
    history = loads(lake)
    assert len(history) == 3
    assert canonical(history[0].rows) == canonical(snapshot_rows())
    assert history[0].number == Decimal(int(FIRST_LOAD.timestamp()))


# --------------------------------------------------------------------------- EC2


def _empty_load(lake: Path, load: str) -> Path:
    """A landed file with the landed columns and no rows."""
    import duckdb

    path = write_load(lake, load, [{}])
    con = duckdb.connect()
    try:
        con.execute(
            f"copy (select * from read_parquet('{path.as_posix()}') where false) to '{path.as_posix()}.tmp' (format parquet)"
        )
    finally:
        con.close()
    Path(f"{path}.tmp").replace(path)
    return path


@pytest.mark.parametrize(
    "latest",
    [
        pytest.param([], id="no-rows"),
        pytest.param([{"ProductId": 1, "Name": "No number", "ModifiedDate": "2014-02-08"}], id="no-product-number"),
        pytest.param([["not", "an", "object"]], id="not-an-object"),
    ],
)
def test_bad_latest_load(monkeypatch, capsys, tmp_path, latest):
    """EC2: a latest load with no rows, or a row whose data is not an object with a ProductNumber:
    exit 1, the file named on stderr, nothing written."""
    lake = tmp_path / "lake"
    write_load(lake, load_id(1), [product(1, "OK-0001", "Fine")])
    bad = write_load(lake, load_id(2), latest) if latest else _empty_load(lake, load_id(2))
    before = hashes(lake)
    code, _, err = run(monkeypatch, capsys, lake, "--seed", "7", "--loads", "1")
    assert code == 1, err
    assert bad.name in err, err
    assert hashes(lake) == before


# --------------------------------------------------------------------------- EC3


@pytest.mark.parametrize(
    "argv",
    [
        pytest.param(["--loads", "0"], id="loads-zero"),
        pytest.param(["--loads", "-1"], id="loads-negative"),
        pytest.param(["--loads", "x"], id="loads-not-integer"),
        pytest.param(["--loads", "1.5"], id="loads-fraction"),
        pytest.param(["--seed", "x"], id="seed-not-integer"),
        pytest.param(["--seed", "-1"], id="seed-negative"),
    ],
)
def test_bad_arguments(monkeypatch, capsys, tmp_path, argv):
    """EC3: --loads 0, a negative or non-integer --loads or --seed: exit 2 with usage, nothing written."""
    lake = tmp_path / "lake"
    code, _, err = run(monkeypatch, capsys, lake, *argv)
    assert code == 2, err
    assert "usage" in err.lower(), err
    assert every_file(lake) == []

    live = tmp_path / "live"
    write_load(live, load_id(1), [product(1, "OK-0001", "Fine")])
    before = hashes(live)
    code, _, err = run(monkeypatch, capsys, live, *argv)
    assert code == 2, err
    assert hashes(live) == before


# --------------------------------------------------------------------------- EC4


def test_clock_behind(monkeypatch, capsys, tmp_path):
    """EC4: the latest load is stamped an hour ahead of the clock: the new load id is one second after
    it, and the ids keep increasing."""
    lake = tmp_path / "lake"
    ahead = f"{int(time.time()) + 3600}.5"
    write_load(lake, load_id(1), [product(i, f"CB-{i:04d}", f"Clock {i}") for i in range(1, 101)])
    write_load(lake, ahead, [product(i, f"CB-{i:04d}", f"Clock {i}") for i in range(1, 101)])
    code, _, err = run(monkeypatch, capsys, lake, "--seed", "7", "--loads", "2")
    assert code == 0, err
    added = [load for load in loads(lake) if load.number > Decimal(ahead)]
    assert len(added) == 2, [load.load_id for load in loads(lake)]
    assert added[0].number == Decimal(ahead) + 1, added[0].load_id
    assert added[1].number > added[0].number
    for load in added:
        assert_landed_shape(load)
