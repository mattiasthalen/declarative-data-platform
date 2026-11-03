"""Simulate source change: append seeded, changed copies of the latest Products and ProductSubcategories loads (ADR-0027).

Beside each Products load it lands a ProductSubcategories load, the latest one with a subcategory
renamed, so the subcategory a product is in, and the subcategory's name, change too (story #6).

``uv run simulate [--seed N] [--loads K]`` appends K loads to ``$LAKE_ROOT`` in dlt's landed
shape, ``adventure_works__products/date=YYYY-MM-DD/hour=HH/<load_id>.<file_id>.parquet`` with the
columns ``data``, ``_dlt_load_id`` and ``_dlt_id``. Each load is the one before with about 5% of
its products changed. On an empty lake the committed snapshot of the feed lands first, at a fixed
time, and the changed loads follow a day apart, so a seed always gives the same lake. On a lake
that holds Products loads, each new load is stamped with the current time, as a real ingest is.
No file already in the lake is ever rewritten or removed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
import time
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

RESOURCE = "adventure_works__products"
SNAPSHOT = Path(__file__).with_name(f"{RESOURCE}.jsonl")
SUBCATEGORIES = "adventure_works__product_subcategories"
SUBCATEGORY_SNAPSHOT = Path(__file__).with_name(f"{SUBCATEGORIES}.jsonl")
SUBCATEGORY = "ProductSubcategoryId"
KEY = "ProductNumber"
CHANGED_AT = "ModifiedDate"
# The attributes the business question reads: the only ones a change touches.
ATTRIBUTES = ("Name", "ProductLine", "Color", "SellStartDate", "SellEndDate", "DiscontinuedDate")
DATES = ("SellStartDate", "SellEndDate", "DiscontinuedDate")
# Snapshot load time on an empty lake: the day after the feed's every ModifiedDate (2014-02-08).
FIRST_LOAD = Decimal(int(datetime(2014, 2, 9, tzinfo=UTC).timestamp()))
DAY = Decimal(86400)
SHARE = 0.05
MIX = (
    ("edit", 50),
    ("correction", 15),
    ("source null", 10),
    ("late arrival", 10),
    ("new product", 5),
    ("drop out", 10),
)
# Beside the mix, each load moves one product to another subcategory and takes one product's away,
# from a random stream of their own, so a seed's other changes stay as they were before story #6.
SUBCATEGORY_KINDS = ("move subcategory", "lose subcategory")


class BadLoad(Exception):
    """The latest load cannot be simulated from."""


# --------------------------------------------------------------------------- the lake


def lake_root() -> Path:
    return Path(os.environ.get("LAKE_ROOT", "lake")).resolve()


def landed_files(lake: Path, resource: str = RESOURCE) -> list[Path]:
    folder = lake / resource
    return sorted(folder.rglob("*.parquet")) if folder.is_dir() else []


def read_load(path: Path) -> tuple[Decimal, list[str]]:
    """A landed file's load id and the JSON text of its rows."""
    import pyarrow.parquet as pq

    table = pq.read_table(path, columns=["data", "_dlt_load_id"])
    ids = [Decimal(value) for value in set(table.column("_dlt_load_id").to_pylist())]
    # A load with no rows carries no id in its rows; its file name starts with it (ADR-0001).
    load_id = max(ids) if ids else Decimal(".".join(path.name.split(".")[:2]))
    return load_id, table.column("data").to_pylist()


def write_load(lake: Path, load_id: str, rows: list[dict], ids: list[str], resource: str = RESOURCE) -> Path:
    """Write one load of ``rows`` of ``resource`` in the landed shape; return the file."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    landed = datetime.fromtimestamp(float(load_id), UTC)
    folder = lake / resource / f"date={landed:%Y-%m-%d}" / f"hour={landed:%H}"
    folder.mkdir(parents=True, exist_ok=True)
    data = [json.dumps(row) for row in rows]
    file_id = hashlib.sha256("".join(ids).encode()).hexdigest()[:10]
    path = folder / f"{load_id}.{file_id}.parquet"
    table = pa.table(
        {
            "data": pa.array(data, pa.string()),
            "_dlt_load_id": pa.array([load_id] * len(rows), pa.string()),
            "_dlt_id": pa.array(ids, pa.string()),
        }
    )
    # Written under another name first, so a build reading the lake never sees half a file.
    partial = path.with_name(path.name + ".partial")
    pq.write_table(table, partial)
    partial.replace(path)
    return path


def parse_rows(path: str, data: list[str]) -> list[dict]:
    """The rows of the load to start from; refused when there is nothing to simulate from."""
    if not data:
        raise BadLoad(f"{path} holds no rows")
    rows = []
    for text in data:
        try:
            row = json.loads(text)
        except (TypeError, ValueError) as error:
            raise BadLoad(f"{path} holds a row that is not JSON: {error}") from error
        if not isinstance(row, dict) or not row.get(KEY):
            raise BadLoad(f"{path} holds a row that is not an object with a {KEY}")
        rows.append(row)
    return rows


# --------------------------------------------------------------------------- changing a load


class Simulation:
    """The seeded state of one run: what has been seen, and what is held back for a load."""

    def __init__(self, seed: int, rows: list[dict], seen: list[dict], subcategories: list[dict] = ()):
        self.seed = seed
        self.rows = rows
        self.subcategories = [dict(row) for row in subcategories]
        self.held_back: dict[str, dict] = {}
        self.numbers = {row.get(KEY) for row in seen}
        self.ids = {row.get("ProductId") for row in seen if isinstance(row.get("ProductId"), int)}

    def values(self, attribute: str) -> list:
        return sorted({row.get(attribute) for row in self.rows if row.get(attribute) is not None}, key=str)

    def next_load(self, index: int, day: date, final: bool) -> list[dict]:
        """The next load's rows: the previous load, back-from-drop products restored, changed.

        Within a run that completes, a product drops out for one load only: the run's ``final`` load
        drops none, since no later load would bring it back, and a product just back is not dropped
        again. Those drop outs are edits instead. A run stopped between a drop out and the next load
        leaves the product out, and no later run brings it back (ADR-0027 addendum).
        """
        rng = random.Random(f"{self.seed}:{index}")
        rows = {row[KEY]: dict(row) for row in self.rows}
        rows.update({number: dict(row) for number, row in self.held_back.items()})
        returning, self.held_back = set(self.held_back), {}
        candidates = sorted(rows)
        count = max(len(MIX), round(len(self.rows) * SHARE))
        kinds = self.kinds(rng, count)
        if final:
            kinds = ["edit" if kind == "drop out" else kind for kind in kinds]
        picked = rng.sample(candidates, min(len(candidates), sum(1 for k in kinds if k != "new product")))
        targets = iter(picked)
        new_rows = []
        for kind in kinds:
            if kind == "new product":
                new_rows.append(self.new_product(rng, rows))
                continue
            number = next(targets, None)
            if number is None:
                break
            if kind == "drop out" and number not in returning:
                self.held_back[number] = rows.pop(number)
            elif kind == "drop out":
                self.edit_fallback(rng, rows[number], day)
            elif not self.change(rng, rows[number], kind, day):
                self.edit_fallback(rng, rows[number], day)
        if self.subcategories:
            self.change_subcategories(index, rows, set(picked), day)
        out = [rows[number] for number in sorted(rows, key=lambda n: self.order(n, rows))]
        out.extend(new_rows)
        self.rows = out
        return out

    def order(self, number: str, rows: dict) -> tuple:
        product_id = rows[number].get("ProductId")
        return (0, product_id, number) if isinstance(product_id, int) else (1, 0, number)

    @staticmethod
    def kinds(rng: random.Random, count: int) -> list[str]:
        """``count`` change kinds: each kind once, the rest drawn by the mix's weights."""
        names = [kind for kind, _ in MIX]
        weights = [weight for _, weight in MIX]
        drawn = names + rng.choices(names, weights=weights, k=max(0, count - len(names)))
        rng.shuffle(drawn)
        return drawn

    def other_value(self, rng: random.Random, row: dict, attribute: str):
        """Another non-null value for ``attribute``, unlike the row's current one."""
        current = row.get(attribute)
        if attribute == "Name":
            return f"{current or row[KEY]} {rng.choice(('II', 'Pro', 'Lite', 'Plus', 'Sport'))}"
        if attribute in DATES:
            # Kept in order: a sell start moves earlier, an end lands 1 to 1501 days after the sell start.
            start = parse_date(row.get("SellStartDate"))
            if attribute == "SellStartDate":
                # A null start moves back from the earliest end date, so it never lands after one.
                ends = [d for d in (parse_date(row.get(a)) for a in DATES[1:]) if d is not None]
                base = start or min(ends, default=date(2013, 1, 1))
                return (base - timedelta(days=rng.randint(1, 365))).isoformat()
            start = start or date(2013, 1, 1)
            ended = (start + timedelta(days=rng.randint(1, 1500))).isoformat()
            return ended if ended != current else (start + timedelta(days=1501)).isoformat()
        choices = [value for value in self.values(attribute) if value != current]
        return rng.choice(choices) if choices else None

    def change(self, rng: random.Random, row: dict, kind: str, day: date) -> bool:
        """Apply ``kind`` to ``row``; False if it cannot apply to this row."""
        if kind == "move subcategory":
            choices = sorted({r[SUBCATEGORY] for r in self.subcategories} - {row.get(SUBCATEGORY)})
            if not choices:
                return False
            row[SUBCATEGORY] = rng.choice(choices)
            row[CHANGED_AT] = day.isoformat()
            return True
        if kind == "lose subcategory":
            if row.get(SUBCATEGORY) is None:
                return False
            row[SUBCATEGORY] = None
            row[CHANGED_AT] = day.isoformat()
            return True
        if kind == "source null":
            held = [a for a in ATTRIBUTES if row.get(a) is not None]
            if not held:
                return False
            row[rng.choice(held)] = None
            row[CHANGED_AT] = day.isoformat()
            return True
        attribute = rng.choice(ATTRIBUTES)
        value = self.other_value(rng, row, attribute)
        if value is None:
            return False
        if kind == "late arrival":
            was = parse_date(row.get(CHANGED_AT))
            if was is None:
                return False
            row[attribute] = value
            row[CHANGED_AT] = (was - timedelta(days=1)).isoformat()
            return True
        row[attribute] = value
        if kind == "edit":
            row[CHANGED_AT] = day.isoformat()
        return True  # a correction keeps ModifiedDate

    def change_subcategories(self, index: int, rows: dict, changed: set, day: date) -> None:
        """Apply each of SUBCATEGORY_KINDS to one product this load has not changed otherwise."""
        rng = random.Random(f"{self.seed}:{index}:subcategory kinds")
        untouched = [n for n in sorted(rows) if n not in changed and n not in self.held_back]
        for kind in SUBCATEGORY_KINDS:
            for number in rng.sample(untouched, len(untouched)):
                if self.change(rng, rows[number], kind, day):
                    untouched.remove(number)
                    break

    def next_subcategories(self, index: int, day: date) -> list[dict]:
        """The next subcategories load: the latest, with one subcategory a product is in renamed at ``day``."""
        rng = random.Random(f"{self.seed}:{index}:subcategories")
        rows = [dict(row) for row in self.subcategories]
        held = {row.get(SUBCATEGORY) for row in self.rows}
        candidates = [row for row in rows if row.get(SUBCATEGORY) in held]
        if candidates:
            renamed = rng.choice(candidates)
            renamed["Name"] = f"{renamed['Name']} {rng.choice(('II', 'Pro', 'Lite', 'Plus', 'Sport'))}"
            renamed[CHANGED_AT] = day.isoformat()
        self.subcategories = rows
        return rows

    def edit_fallback(self, rng: random.Random, row: dict, day: date) -> None:
        row["Name"] = self.other_value(rng, row, "Name")
        row[CHANGED_AT] = day.isoformat()

    def new_product(self, rng: random.Random, rows: dict) -> dict:
        """A product number never seen: a copy of an existing product with a new id, number and name."""
        template = dict(rows[rng.choice(sorted(rows))])
        product_id = max(self.ids | {0}) + 1
        self.ids.add(product_id)
        number = f"SM-{product_id:04d}"
        while number in self.numbers:
            number += "X"
        self.numbers.add(number)
        template["ProductId"] = product_id
        template[KEY] = number
        template["Name"] = f"Simulated {number}"
        if "Rowguid" in template:
            template["Rowguid"] = str(uuid.UUID(int=rng.getrandbits(128)))
        return template


def parse_date(value) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def dlt_ids(start: str, seed: int, index: int, count: int) -> list[str]:
    """14-character row ids, as dlt's ``_dlt_id`` is: the same for the same starting load and seed,
    and different for another starting load, so a seed reused on a grown lake repeats no id."""
    return [hashlib.sha256(f"{start}:{seed}:{index}:{n}".encode()).hexdigest()[:14] for n in range(count)]


def format_id(value: Decimal) -> str:
    return f"{value:.6f}"


# --------------------------------------------------------------------------- the command


def parse(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="simulate",
        description="Append seeded, changed copies of the latest Products and ProductSubcategories loads to $LAKE_ROOT.",
    )
    parser.add_argument("--seed", type=int, help="seed for the changes (default: random, printed)")
    parser.add_argument("--loads", type=int, default=1, help="how many changed loads to append (default 1)")
    args = parser.parse_args(argv)
    if args.loads < 1:
        parser.error("--loads must be a positive integer")
    if args.seed is not None and args.seed < 0:
        parser.error("--seed must be a non-negative integer")
    return args


def latest_subcategories(lake: Path) -> list[dict]:
    """The rows of the latest ProductSubcategories load in ``lake``; none if it holds none."""
    by_load: dict[Decimal, list[str]] = {}
    for path in landed_files(lake, SUBCATEGORIES):
        load_id, data = read_load(path)
        by_load.setdefault(load_id, []).extend(data)
    if not by_load:
        return []
    return [row for row in safe_rows(by_load[max(by_load)]) if isinstance(row.get(SUBCATEGORY), int)]


def run(seed: int, loads: int, lake: Path) -> list[Path]:
    """Append ``loads`` changed loads to ``lake``, landing the snapshots first on an empty lake."""
    files = landed_files(lake)
    paths: list[Path] = []
    if files:
        # One load can span several files; the latest load is all of its files' rows.
        by_load: dict[Decimal, tuple[list[str], list[str]]] = {}
        for path in files:
            load_id, data = read_load(path)
            names, rows_text = by_load.setdefault(load_id, ([], []))
            names.append(str(path))
            rows_text.extend(data)
        latest_id = max(by_load)
        rows = parse_rows(", ".join(by_load[latest_id][0]), by_load[latest_id][1])
        seen = [row for _, data in by_load.values() for row in safe_rows(data)]
        simulation = Simulation(seed, rows, seen, latest_subcategories(lake))
        start, stamp, stamp_now = format_id(latest_id), latest_id, True
    else:
        rows = [json.loads(line) for line in SNAPSHOT.read_text().splitlines() if line.strip()]
        subcategories = [json.loads(line) for line in SUBCATEGORY_SNAPSHOT.read_text().splitlines() if line.strip()]
        simulation = Simulation(seed, rows, rows, subcategories)
        start, stamp, stamp_now = format_id(FIRST_LOAD), FIRST_LOAD, False
        paths.append(write_load(lake, start, rows, dlt_ids(start, seed, 0, len(rows))))
        paths.append(
            write_load(lake, start, subcategories, dlt_ids(f"{start}:s", seed, 0, len(subcategories)), SUBCATEGORIES)
        )
    for index in range(1, loads + 1):
        if stamp_now:
            # Now, as a real ingest stamps a load; one second after the latest if the clock is behind (A3).
            now = Decimal(format_id(Decimal(repr(time.time()))))  # compared as it will be written
            stamp = now if now > stamp else stamp + 1
        else:
            stamp = stamp + DAY
        day = datetime.fromtimestamp(float(stamp), UTC).date()
        load_rows = simulation.next_load(index, day, final=index == loads)
        paths.append(write_load(lake, format_id(stamp), load_rows, dlt_ids(start, seed, index, len(load_rows))))
        if simulation.subcategories:
            renamed = simulation.next_subcategories(index, day)
            ids = dlt_ids(f"{start}:s", seed, index, len(renamed))
            paths.append(write_load(lake, format_id(stamp), renamed, ids, SUBCATEGORIES))
    return paths


def safe_rows(data: list[str]) -> list[dict]:
    out = []
    for text in data:
        try:
            row = json.loads(text)
        except (TypeError, ValueError):
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def main(argv: list[str] | None = None) -> int:
    args = parse(argv)
    seed = args.seed if args.seed is not None else random.SystemRandom().randrange(2**31)
    print(f"seed {seed}")
    lake = lake_root()
    try:
        paths = run(seed, args.loads, lake)
    except BadLoad as error:
        print(f"simulate: {error}", file=sys.stderr)
        return 1
    for path in paths:
        print(path.relative_to(lake).as_posix())
    return 0
