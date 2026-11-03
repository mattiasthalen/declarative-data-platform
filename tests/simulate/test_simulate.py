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
import os
import re
import shutil
import socket
import subprocess
import time
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from itertools import pairwise
from pathlib import Path

import pytest

from harness import REPO, RESOURCE, SUBCATEGORIES, load_id, product, write_load

SNAPSHOT = REPO / "src" / "simulate" / "adventure_works__products.jsonl"
# Story #6: the committed ProductSubcategories snapshot, landed beside the Products one (A20).
SUBCATEGORY_SNAPSHOT = REPO / "src" / "simulate" / f"{SUBCATEGORIES}.jsonl"
SUBCATEGORY_FIELDS = {"ProductSubcategoryId", "ProductCategoryId", "Name", "Rowguid", "ModifiedDate"}
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
    """The kind of one product's change, from its row before and after; ``unknown`` if none fits.
    A subcategory moved or lost (story #6) is an edit or a source null of ``ProductSubcategoryId``."""
    attributes = [k for k in (*BUSINESS, "ProductSubcategoryId") if before.get(k) != after.get(k)]
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
    beside = [p for p in every_file(lake) if p.relative_to(lake).parts[0] != SUBCATEGORIES]
    assert len(beside) == 7, beside
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
            assert moved <= set(BUSINESS) | {"ModifiedDate", "ProductSubcategoryId"}, f"{number} changed {moved}"
            assert kind != "unknown", f"{number} changed in no known way: {previous} -> {row}"
        total += found["kinds"]
    missing = [kind for kind in KINDS if not total[kind]]
    assert not missing, f"seed 7 never made a {missing}; it made {dict(total)}"

    # Story #6 AC14: a product moves subcategory, a product loses it, a subcategory is renamed.
    subcategory_kinds = Counter()
    known = {row["ProductSubcategoryId"] for load in subcategory_loads(lake) for row in load.rows}
    for found in diff(history):
        day = found["load"].day
        for number, (previous, row, _) in found["changed"].items():
            was, now = previous.get("ProductSubcategoryId"), row.get("ProductSubcategoryId")
            if was is None or was == now:
                continue
            kind = "lose subcategory" if now is None else "move subcategory"
            if modified(row) == day:
                subcategory_kinds[kind] += 1
            if now is not None:
                assert now in known, f"{number} moved to subcategory {now}, which never landed"
    subcategory_kinds["rename subcategory"] = len(renames(lake, history))
    missing = [k for k in ("move subcategory", "lose subcategory", "rename subcategory") if not subcategory_kinds[k]]
    assert not missing, f"seed 7 never made a {missing} (with ModifiedDate moved); it made {dict(subcategory_kinds)}"


def test_change_kinds_subcategory_snapshot(seven):
    """Story #6 AC14 ([14]): an empty lake's first subcategories load is the committed snapshot, the 37
    ProductSubcategories rows the feed served, in the landed shape."""
    lake, code = seven
    assert code == 0, f"simulate --seed 7 --loads 6 ended with {code}"
    assert SUBCATEGORY_SNAPSHOT.is_file(), f"no committed {SUBCATEGORY_SNAPSHOT.relative_to(REPO)}"
    rows = [json.loads(line) for line in SUBCATEGORY_SNAPSHOT.read_text().splitlines() if line.strip()]
    assert len(rows) == 37, f"the subcategory snapshot holds {len(rows)} rows, the feed 37"
    assert all(set(row) == SUBCATEGORY_FIELDS for row in rows), "a snapshot row has other fields than the feed's"
    landed = subcategory_loads(lake)
    assert landed, f"simulate landed no {SUBCATEGORIES} load"
    for load in landed:
        assert set(load.columns) == LANDED, f"{load.path.name} has columns {load.columns}"
        assert load.path.relative_to(lake).parts[0] == SUBCATEGORIES, load.path
    assert canonical(landed[0].rows) == canonical(rows)


def subcategory_loads(lake: Path) -> list["Load"]:
    """Every ProductSubcategories load in the lake, in load-id order."""
    folder = lake / SUBCATEGORIES
    paths = sorted(folder.rglob("*.parquet")) if folder.exists() else []
    return sorted((Load(p) for p in paths), key=lambda load: load.number)


def renames(lake: Path, history: list["Load"]) -> list[tuple]:
    """(subcategory id, old name, new name) of each subcategory renamed while a product was in it, from the
    subcategory loads in order: a name unlike the one last landed for that id."""
    referenced = {row.get("ProductSubcategoryId") for load in history for row in load.rows}
    names: dict = {}
    found = []
    for load in subcategory_loads(lake):
        for row in load.rows:
            ident, name = row["ProductSubcategoryId"], row["Name"]
            if ident in names and names[ident] != name and ident in referenced:
                found.append((ident, names[ident], name))
            names[ident] = name
    return found


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
                nulled = [
                    k
                    for k in (*BUSINESS, "ProductSubcategoryId")
                    if previous.get(k) is not None and row.get(k) is None
                ]
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
    # go-task colours its listing under FORCE_COLOR, as in GitHub Actions;
    # NO_COLOR asks it not to, and stripping ANSI escapes covers a go-task that colours anyway.
    listed = subprocess.run(
        ["uv", "run", "task", "--list"],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=300,
        env={**os.environ, "NO_COLOR": "1"},
    )
    assert listed.returncode == 0, listed.stdout + listed.stderr
    listing = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", listed.stdout)
    assert re.search(r"^\*\s+simulate:", listing, re.MULTILINE), listed.stdout
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


# --------------------------------------------------------------------------- review findings
#
# Regression tests for the findings of story #25's reviews (round 1 and the gate's G-findings).


MANY_SEEDS = range(50)


@pytest.fixture(scope="module")
def many(tmp_path_factory):
    """Per seed 0..49: the ProductNumbers of each load, in load-id order, of ``simulate --seed s
    --loads 6`` on an empty lake, or what the run ended with."""
    import simulate

    out = {}
    for seed in MANY_SEEDS:
        lake = tmp_path_factory.mktemp(f"seed{seed}") / "lake"
        lake.mkdir()
        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("LAKE_ROOT", str(lake))
            try:
                code = simulate.main(["--seed", str(seed), "--loads", "6"])
            except SystemExit as exit_:
                code = exit_.code
            except Exception as error:  # noqa: BLE001
                code = repr(error)
        out[seed] = (code, _numbers_per_load(lake))
    return out


def _numbers_per_load(lake: Path) -> list[tuple[str, set[str]]]:
    """(load id, its ProductNumbers) of every Products load in ``lake``, in load-id order: one query."""
    import duckdb

    if not files(lake):
        return []
    con = duckdb.connect()
    try:
        rows = con.execute(
            f"""
            select cast(_dlt_load_id as varchar), json_extract_string(cast(data as varchar), '$.ProductNumber')
            from read_parquet('{(lake / RESOURCE).as_posix()}/**/*.parquet', hive_partitioning = false)
            """
        ).fetchall()
    finally:
        con.close()
    per_load: dict[str, set[str]] = {}
    for load, number in rows:
        per_load.setdefault(load, set()).add(number)
    return sorted(per_load.items(), key=lambda item: Decimal(item[0]))


def test_dropped_product_back_in_next_load_many_seeds(many):
    """G1 (AC4, spec [3]): a product absent from load n (dropped there) is present again in load n+1;
    no product is absent from two loads in a row. Seeds 0..49, 6 loads each, empty lake."""
    failures = []
    for seed, (code, history) in many.items():
        assert code == 0, f"seed {seed}: simulate ended with {code}"
        assert len(history) == 7, f"seed {seed}: {len(history)} loads"
        seen: set[str] = set(history[0][1])
        for n in range(1, len(history) - 1):
            (load, numbers), (next_load, next_numbers) = history[n], history[n + 1]
            seen |= numbers
            absent_twice = (seen - numbers) - next_numbers
            if absent_twice:
                failures.append(f"seed {seed}: {sorted(absent_twice)} absent from load {load} and from {next_load}")
    assert not failures, "\n".join(failures)


def test_last_load_drops_none_many_seeds(many):
    """G4 / round-1 F1 (spec [3], amended): a run's last load drops no product: every product of the
    load before it is in it. Seeds 0..49, 6 loads each, empty lake."""
    failures = []
    for seed, (code, history) in many.items():
        assert code == 0, f"seed {seed}: simulate ended with {code}"
        assert len(history) == 7, f"seed {seed}: {len(history)} loads"
        (_, before), (last, numbers) = history[-2], history[-1]
        if before - numbers:
            failures.append(f"seed {seed}: last load {last} drops {sorted(before - numbers)}")
    assert not failures, "\n".join(failures)


def test_last_load_drops_none_seed_7(seven):
    """G4 / round-1 F1: seed 7's last load drops no product, and a product dropped in the load before
    it is back in it."""
    lake, code = seven
    assert code == 0, f"simulate --seed 7 --loads 6 ended with {code}"
    history = loads(lake)
    assert len(history) == 7
    found = diff(history)
    assert not found[-1]["dropped"], f"the last load {history[-1].load_id} drops {sorted(found[-1]['dropped'])}"
    last = history[-1].by_number()
    assert not [n for n in found[-2]["dropped"] if n not in last]


def test_live_lake_stamps_each_load_at_the_clock(monkeypatch, capsys, tmp_path):
    """Round-1 F2 (spec [4]): on a lake whose latest load is in the past, each new load id is the
    current time when it is written: within about a second of the wall clock, never a second or more
    ahead of it, strictly increasing; not the first stamp plus 1 s, 2 s..."""
    lake = tmp_path / "lake"
    _hand_written_lake(lake)
    existing = {load.load_id for load in loads(lake)}
    started = time.time()
    code, _, err = run(monkeypatch, capsys, lake, "--seed", "7", "--loads", "3")
    finished = time.time()
    assert code == 0, err
    added = [load for load in loads(lake) if load.load_id not in existing]
    assert len(added) == 3, [load.load_id for load in added]
    for earlier, later in pairwise(added):
        assert earlier.number < later.number, (earlier.load_id, later.load_id)
    for load in added:
        stamp = float(load.load_id)
        written = load.path.stat().st_mtime
        assert stamp >= started - 1, (load.load_id, started)
        assert stamp < finished + 1, f"load {load.load_id} is ahead of the clock (run ended at {finished:.3f})"
        assert stamp - written < 1, f"load {load.load_id} is {stamp - written:.3f}s ahead of its file's write time"
        assert written - stamp < 2, f"load {load.load_id} is {written - stamp:.3f}s behind its file's write time"


def test_same_seed_live_runs_share_no_dlt_id(monkeypatch, capsys, tmp_path):
    """Round-1 F3: two live runs with the same --seed on the same lake, the second starting from the
    first's output, share no `_dlt_id`."""
    lake = tmp_path / "lake"
    _hand_written_lake(lake)
    existing = {load.load_id for load in loads(lake)}
    code, _, err = run(monkeypatch, capsys, lake, "--seed", "7", "--loads", "2")
    assert code == 0, err
    first = [load for load in loads(lake) if load.load_id not in existing]
    assert len(first) == 2
    existing |= {load.load_id for load in first}
    code, _, err = run(monkeypatch, capsys, lake, "--seed", "7", "--loads", "2")
    assert code == 0, err
    second = [load for load in loads(lake) if load.load_id not in existing]
    assert len(second) == 2
    first_ids = {r[2] for load in first for r in load.raw}
    second_ids = {r[2] for load in second for r in load.raw}
    shared = first_ids & second_ids
    assert not shared, f"{len(shared)} _dlt_ids in both runs, e.g. {sorted(shared)[:5]}"


def test_latest_load_split_over_two_files(monkeypatch, capsys, tmp_path):
    """Round-1 F4: when the latest load id is split over two Parquet files, the run starts from the rows
    of both files."""
    lake = tmp_path / "lake"
    write_load(lake, load_id(1), [product(1000 + i, f"OL-{i:04d}", f"Older {i}") for i in range(50)])
    part_a = [product(2000 + i, f"PA-{i:04d}", f"Part A {i}") for i in range(100)]
    part_b = [product(3000 + i, f"PB-{i:04d}", f"Part B {i}") for i in range(100)]
    write_load(lake, load_id(2), part_a)
    write_load(lake, load_id(2), part_b)
    existing = {load_id(1), load_id(2)}
    code, _, err = run(monkeypatch, capsys, lake, "--seed", "7", "--loads", "1")
    assert code == 0, err
    added = [load for load in files(lake) if not any(load.name.startswith(e + ".") for e in existing)]
    assert len(added) == 1, added
    numbers = Load(added[0]).by_number().keys()
    for label, part in (("A", part_a), ("B", part_b)):
        held = numbers & {row["ProductNumber"] for row in part}
        assert len(held) >= 0.9 * len(part), f"the new load holds {len(held)} of file {label}'s {len(part)} products"
    assert not numbers & {f"OL-{i:04d}" for i in range(50)}, "the new load starts from the older load"


def _day(value) -> date | None:
    return None if value is None else date.fromisoformat(str(value)[:10])


def test_changed_rows_end_on_or_after_start(seven):
    """Round-1 F10: in every simulated load of seed 7, a row the simulator changed that holds a
    SellStartDate and a SellEndDate, or a SellStartDate and a DiscontinuedDate, has the end on or after
    the start. The snapshot's own rows are as served and not checked."""
    lake, code = seven
    assert code == 0, f"simulate --seed 7 --loads 6 ended with {code}"
    bad = []
    for found in diff(loads(lake)):
        for number, (_, row, kind) in found["changed"].items():
            start = _day(row.get("SellStartDate"))
            if start is None:
                continue
            for end_key in ("SellEndDate", "DiscontinuedDate"):
                end = _day(row.get(end_key))
                if end is not None and end < start:
                    bad.append(f"load {found['load'].load_id}: {number} ({kind}) {end_key} {end} < SellStartDate {start}")
    assert not bad, "\n".join(bad)


@pytest.mark.parametrize("lake_kind", ["empty", "live"])
def test_no_leftover_files(monkeypatch, capsys, tmp_path, lake_kind):
    """Round-1 F17: after a run, nothing but `*.parquet` landed files lies under the resource folder:
    no temporary file is left behind."""
    lake = tmp_path / "lake"
    if lake_kind == "live":
        _hand_written_lake(lake)
    code, _, err = run(monkeypatch, capsys, lake, "--seed", "7", "--loads", "3")
    assert code == 0, err
    stray = [p for p in (lake / RESOURCE).rglob("*") if p.is_file() and p.suffix != ".parquet"]
    assert not stray, stray
    assert all(p.name.count(".") >= 2 for p in files(lake)), files(lake)


# --------------------------------------------------------------------------- story #4: dates in order

LONG_SEEDS, LONG_LOADS = range(20), 200


@pytest.fixture(scope="module")
def long_runs(tmp_path_factory):
    """Per seed 0..19: the exit code of ``simulate --seed s --loads 200`` on an empty lake, and the lake."""
    import simulate

    out = {}
    for seed in LONG_SEEDS:
        lake = tmp_path_factory.mktemp(f"long{seed}") / "lake"
        lake.mkdir()
        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("LAKE_ROOT", str(lake))
            try:
                code = simulate.main(["--seed", str(seed), "--loads", str(LONG_LOADS)])
            except SystemExit as exit_:
                code = exit_.code
        out[seed] = (code, lake)
    return out


def test_dates_in_order(long_runs):
    """AC8, EC7: over 200-load runs for seeds 0..19, no landed row has a SellStartDate after its
    SellEndDate or after its DiscontinuedDate, when either is set."""
    import duckdb

    bad, paired = [], 0
    for seed, (code, lake) in long_runs.items():
        assert code == 0, f"seed {seed}: simulate ended with {code}"
        assert len(files(lake)) == LONG_LOADS + 1, f"seed {seed}: {len(files(lake))} loads"

        def day(field: str) -> str:
            return f"try_cast(left(json_extract_string(cast(data as varchar), '$.{field}'), 10) as date)"

        con = duckdb.connect()
        try:
            rows = con.execute(
                f"""
                with r as (
                    select cast(_dlt_load_id as varchar) as load,
                        json_extract_string(cast(data as varchar), '$.ProductNumber') as number,
                        {day('SellStartDate')} as start, {day('SellEndDate')} as ended,
                        {day('DiscontinuedDate')} as discontinued
                    from read_parquet('{(lake / RESOURCE).as_posix()}/**/*.parquet', hive_partitioning = false)
                )
                select load, number, start, ended, discontinued,
                    count(*) filter (where start is not null and (ended is not null or discontinued is not null))
                        over () as paired
                from r
                """
            ).fetchall()
        finally:
            con.close()
        paired += rows[0][5] if rows else 0
        for load, number, start, ended, discontinued, _ in rows:
            if start is None:
                continue
            if (ended is not None and start > ended) or (discontinued is not None and start > discontinued):
                bad.append(
                    f"seed {seed} load {load}: {number} starts {start}, ends {ended}, discontinued {discontinued}"
                )
    assert paired > 0, "no row holds a sell start and an end date: the check proves nothing"
    assert not bad, f"{len(bad)} rows out of order, e.g.:\n" + "\n".join(bad[:20])


def test_null_start_lands_before_end():
    """AC8, EC7: a sell start set on a row whose sell start is null lands 1 to 365 days before the row's
    earliest set end date (SellEndDate, DiscontinuedDate), and with neither set, 1 to 365 days before
    2013-01-01."""
    import random

    import simulate

    rows = snapshot_rows()
    simulation = simulate.Simulation(0, rows, rows)
    cases = [
        ("2012-03-10", None, date(2012, 3, 10)),
        (None, "2011-08-01", date(2011, 8, 1)),
        ("2012-03-10", "2011-08-01", date(2011, 8, 1)),
        ("2011-08-01", "2012-03-10", date(2011, 8, 1)),
        (None, None, date(2013, 1, 1)),
    ]
    wrong = []
    for ended, discontinued, anchor in cases:
        for draw in range(300):
            row = dict(rows[0], SellStartDate=None, SellEndDate=ended, DiscontinuedDate=discontinued)
            value = simulation.other_value(random.Random(draw), row, "SellStartDate")
            start = date.fromisoformat(str(value)[:10])
            if not anchor - timedelta(days=365) <= start < anchor:
                wrong.append(f"end {ended}, discontinued {discontinued}: start {start}, expected 1 to 365 days before {anchor}")
    assert not wrong, f"{len(wrong)} starts out of range, e.g.:\n" + "\n".join(wrong[:10])
