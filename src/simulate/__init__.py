"""Simulate source change: append seeded, changed copies of the latest Products load (ADR-0020).

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


class BadLoad(Exception):
    """The latest load cannot be simulated from."""


# --------------------------------------------------------------------------- the lake


def lake_root() -> Path:
    return Path(os.environ.get("LAKE_ROOT", "lake")).resolve()


def landed_files(lake: Path) -> list[Path]:
    folder = lake / RESOURCE
    return sorted(folder.rglob("*.parquet")) if folder.is_dir() else []


def read_load(path: Path) -> tuple[Decimal, list[str]]:
    """A landed file's load id and the JSON text of its rows."""
    import pyarrow.parquet as pq

    table = pq.read_table(path, columns=["data", "_dlt_load_id"])
    ids = [Decimal(value) for value in set(table.column("_dlt_load_id").to_pylist())]
    # A load with no rows carries no id in its rows; its file name starts with it (ADR-0001).
    load_id = max(ids) if ids else Decimal(".".join(path.name.split(".")[:2]))
    return load_id, table.column("data").to_pylist()


def write_load(lake: Path, load_id: str, rows: list[dict], ids: list[str]) -> Path:
    """Write one load of ``rows`` in the landed shape; return the file."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    landed = datetime.fromtimestamp(float(load_id), UTC)
    folder = lake / RESOURCE / f"date={landed:%Y-%m-%d}" / f"hour={landed:%H}"
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
    pq.write_table(table, path)
    return path


def parse_rows(path: Path, data: list[str]) -> list[dict]:
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

    def __init__(self, seed: int, rows: list[dict], seen: list[dict]):
        self.seed = seed
        self.rows = rows
        self.held_back: dict[str, dict] = {}
        self.numbers = {row.get(KEY) for row in seen}
        self.ids = {row.get("ProductId") for row in seen if isinstance(row.get("ProductId"), int)}
        self.names = {row.get("Name") for row in rows}

    def values(self, attribute: str) -> list:
        return sorted({row.get(attribute) for row in self.rows if row.get(attribute) is not None}, key=str)

    def next_load(self, index: int, day: date) -> list[dict]:
        """The next load's rows: the previous load, back-from-drop products restored, changed."""
        rng = random.Random(f"{self.seed}:{index}")
        rows = {row[KEY]: dict(row) for row in self.rows}
        rows.update({number: dict(row) for number, row in self.held_back.items()})
        self.held_back = {}
        candidates = sorted(rows)
        count = max(len(MIX), round(len(self.rows) * SHARE))
        kinds = self.kinds(rng, count)
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
            if kind == "drop out":
                self.held_back[number] = rows.pop(number)
            elif not self.change(rng, rows[number], kind, day):
                self.edit_fallback(rng, rows[number], day)
        out = [rows[number] for number in sorted(rows, key=lambda n: self.order(n, rows))]
        out.extend(new_rows)
        self.names |= {row.get("Name") for row in out}
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
            base = parse_date(current) or parse_date(row.get("SellStartDate")) or date(2013, 1, 1)
            shifted = base + timedelta(days=rng.choice((-1, 1)) * rng.randint(1, 365))
            return shifted.isoformat()
        choices = [value for value in self.values(attribute) if value != current]
        return rng.choice(choices) if choices else None

    def change(self, rng: random.Random, row: dict, kind: str, day: date) -> bool:
        """Apply ``kind`` to ``row``; False if it cannot apply to this row."""
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
            row[CHANGED_AT] = format_like(row.get(CHANGED_AT), was - timedelta(days=1))
            return True
        row[attribute] = value
        if kind == "edit":
            row[CHANGED_AT] = day.isoformat()
        return True  # a correction keeps ModifiedDate

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


def format_like(original, value: date) -> str:
    """``value`` in the shape of ``original``: a plain date, keeping any time part after it."""
    return value.isoformat() + (original[10:] if isinstance(original, str) else "")


def dlt_ids(seed: int, index: int, count: int) -> list[str]:
    """Deterministic 14-character row ids, as dlt's ``_dlt_id`` is."""
    return [hashlib.sha256(f"{seed}:{index}:{n}".encode()).hexdigest()[:14] for n in range(count)]


def format_id(value: Decimal) -> str:
    return f"{value:.6f}"


# --------------------------------------------------------------------------- the command


def positive(text: str) -> int:
    value = int(text)
    if value < 1:
        raise ValueError(text)
    return value


def natural(text: str) -> int:
    value = int(text)
    if value < 0:
        raise ValueError(text)
    return value


positive.__name__ = "positive integer"
natural.__name__ = "non-negative integer"


def parse(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="simulate",
        description="Append seeded, changed copies of the latest Products load to $LAKE_ROOT.",
    )
    parser.add_argument("--seed", type=natural, help="seed for the changes (default: random, printed)")
    parser.add_argument("--loads", type=positive, default=1, help="how many changed loads to append (default 1)")
    return parser.parse_args(argv)


def run(seed: int, loads: int, lake: Path) -> list[Path]:
    """Append ``loads`` changed loads to ``lake``, landing the snapshot first on an empty lake."""
    files = landed_files(lake)
    if files:
        read = [read_load(path) for path in files]
        latest_id, latest_path, latest_data = max((lid, path, data) for (lid, data), path in zip(read, files))
        rows = parse_rows(latest_path, latest_data)
        seen = [row for _, data in read for row in safe_rows(data)]
        stamps, last = [], latest_id
        for _ in range(loads):
            # Now, as a real ingest stamps a load, but always after the latest load (A3).
            last = max(Decimal(repr(time.time())), last + 1)
            stamps.append(last)
        simulation = Simulation(seed, rows, seen)
        start = []
    else:
        rows = [json.loads(line) for line in SNAPSHOT.read_text().splitlines() if line.strip()]
        simulation = Simulation(seed, rows, rows)
        stamps = [FIRST_LOAD + DAY * k for k in range(1, loads + 1)]
        start = [(format_id(FIRST_LOAD), rows)]
    paths = []
    for load_id, load_rows in start:
        paths.append(write_load(lake, load_id, load_rows, dlt_ids(seed, 0, len(load_rows))))
    for index, stamp in enumerate(stamps, 1):
        day = datetime.fromtimestamp(float(stamp), UTC).date()
        load_rows = simulation.next_load(index, day)
        paths.append(write_load(lake, format_id(stamp), load_rows, dlt_ids(seed, index, len(load_rows))))
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
