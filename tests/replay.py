"""The independent answer to the business question over a Products lake (story #25, EC6).

Computed from the lake's rows alone, without dbt: every landed load is read, each row cast as
the Products contract casts it (``ProductLine`` trimmed, dates and ``ModifiedDate`` through
``try_cast``), and ADR-0006's rules are replayed per product and attribute, loads in load-id
order and, within a load, rows in ``ModifiedDate`` order:

- a value at a ChangedAt not held asserts it, unless the reliable version before it has the
  same value (a restatement);
- another value at a held ChangedAt retracts the held one and asserts the new one;
- the same value at a held ChangedAt adds nothing;
- a null retracts the version in effect at its ChangedAt, unless the latest statement about
  that time is already a retraction;
- a value whose cast failed adds nothing; a row without a key or a usable ``ModifiedDate``
  is not loaded;
- a key's lone row that repeats its lone row in the load before is not applied again.

``reliable()`` reads the reliable posits as they are, without a backfill (story #4). The value on
day D is the reliable value with the latest ChangedAt on or before D, else the
earliest reliable value (ADR-0011's first version). A product is on sale on D as #1's approved
business question defines it: sell start on or before D, sell end null or on or after D,
discontinued null or after D. ``on_sale`` counts those products per product line and colour.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

RESOURCE = "adventure_works__products"

# Each attribute PR_Product loads, as conform casts it: JSON field -> SQL over the field's text.
ATTRIBUTES = {
    "ProductNumber": "{}",
    "Name": "{}",
    "ProductLine": "trim({})",
    "Color": "{}",
    "SellStartDate": "try_cast({} as date)",
    "SellEndDate": "try_cast({} as date)",
    "DiscontinuedDate": "try_cast({} as date)",
}


def _rows(lake: Path) -> list[dict]:
    """Every landed Products row, cast as conform casts it."""
    import duckdb

    pattern = (Path(lake) / RESOURCE).as_posix() + "/date=*/hour=*/*.parquet"
    con = duckdb.connect()
    try:
        if not con.execute(f"select count(*) from glob('{pattern}')").fetchone()[0]:
            return []
        selects = []
        for field, cast in ATTRIBUTES.items():
            text = f"json_extract_string(data, '$.{field}')"
            selects.append(f"{cast.format(text)} as \"{field}\"")
            selects.append(
                f"({text} is not null and {cast.format(text)} is null) as \"{field}__cast_failed\""
            )
        cursor = con.execute(
            "select cast(_dlt_load_id as varchar) as load_id, "
            "json_extract_string(data, '$.ProductNumber') as number, "
            "try_cast(json_extract_string(data, '$.ModifiedDate') as timestamp) as changed_at, "
            + ", ".join(selects)
            + f" from read_parquet('{pattern}', hive_partitioning = false)"
        )
        names = [d[0] for d in cursor.description]
        return [dict(zip(names, row)) for row in cursor.fetchall()]
    finally:
        con.close()


class _Attribute:
    """One product's one attribute: every posit it holds, as [changed_at, value, reliability]."""

    def __init__(self) -> None:
        self.state: list[list] = []

    def apply(self, changed_at: datetime, value, cast_failed: bool) -> None:
        if cast_failed:
            return
        if value is None:
            earlier = [p[0] for p in self.state if p[0] <= changed_at]
            if not earlier:
                return
            retract_at = max(earlier)
            for p in self.state:
                if p[0] == retract_at and p[2] == 1:
                    p[2] = 0
            return
        held = any(p[0] == changed_at and p[2] == 1 and p[1] == value for p in self.state)
        before = sorted(
            ((p[0], p[1]) for p in self.state if p[0] < changed_at and p[2] == 1), key=lambda p: (p[0], p[1])
        )
        restates = bool(before) and before[-1][1] == value
        asserts = not held and not restates
        posited = any(p[0] == changed_at and p[1] == value for p in self.state)
        for p in self.state:
            if p[0] == changed_at and p[2] == 1 and p[1] != value:
                p[2] = 0
            elif asserts and p[0] == changed_at and p[1] == value:
                p[2] = 1
        if asserts and not posited:
            self.state.append([changed_at, value, 1])

    def reliable(self) -> list[tuple]:
        """(ChangedAt, value) of every reliable posit, in ChangedAt order: what integrate holds, before
        ``on()``'s backfill of the earliest value, which is serve's alone."""
        return sorted(((p[0], p[1]) for p in self.state if p[2] == 1), key=lambda p: p[0])

    def on(self, day: date):
        reliable = [p for p in self.state if p[2] == 1]
        if not reliable:
            return None
        held = [p for p in reliable if p[0].date() <= day]
        if held:
            return max(held, key=lambda p: p[0])[1]
        return min(reliable, key=lambda p: p[0])[1]


def products(lake: Path) -> dict[str, dict[str, _Attribute]]:
    """ProductNumber -> attribute -> what it holds after every load in the lake."""
    by_key: dict[str, list[dict]] = defaultdict(list)
    for row in _rows(lake):
        if row["number"] is None or row["changed_at"] is None:
            continue
        by_key[row["number"]].append(row)

    held: dict[str, dict[str, _Attribute]] = {}
    for number, rows in by_key.items():
        per_load: dict[Decimal, list[dict]] = defaultdict(list)
        for row in rows:
            per_load[Decimal(row["load_id"])].append(row)
        attributes = {field: _Attribute() for field in ATTRIBUTES}
        for field, attribute in attributes.items():
            before: list[dict] | None = None
            for load in sorted(per_load):
                in_load = sorted(
                    per_load[load], key=lambda r: (r["changed_at"], r[field] is not None, str(r[field]))
                )

                def statement(r: dict) -> tuple:
                    return (r[field], r["changed_at"], r[f"{field}__cast_failed"])

                repeats = (
                    len(in_load) == 1
                    and before is not None
                    and len(before) == 1
                    and statement(in_load[0]) == statement(before[0])
                )
                if not repeats:
                    for r in in_load:
                        attribute.apply(r["changed_at"], r[field], r[f"{field}__cast_failed"])
                before = in_load
        held[number] = attributes
    return held


def _as_date(value) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def on_sale(lake: Path, day) -> list[tuple]:
    """(product line, colour, count) of the products on sale on ``day``, sorted."""
    day = _as_date(day)
    counts: dict[tuple, int] = defaultdict(int)
    for attributes in products(lake).values():
        value = {field: attribute.on(day) for field, attribute in attributes.items()}
        start, end, disc = value["SellStartDate"], value["SellEndDate"], value["DiscontinuedDate"]
        if start is None or start > day:
            continue
        if end is not None and end < day:
            continue
        if disc is not None and not day < disc:
            continue
        counts[(value["ProductLine"], value["Color"])] += 1
    return sorted(((line, color, n) for (line, color), n in counts.items()), key=repr)
