"""Story #6's story lake: products tied to their subcategories over five loads (spec story-6).

Each step lands its loads and builds; a snapshot is kept after every good build:

    L1  subcategories 1 Mountain Bikes, 2 Road Bikes, 4 Bottom Brackets;
        SN-0001 in 1, SN-0002 in none, SN-0003 in 2, SN-0004 in 3 (not landed yet),
        SN-0005 in 1, SN-0006 in 2, all at 2014-02-08                              build
    L2  subcategory 3 Touring Bikes lands; the products repeat L1                   build
    L3  SN-0001 moves to 2 and is renamed at 2014-03-01 (EC2); SN-0003's subcategory
        is nulled at 2014-03-01; SN-0005 is restated unchanged at 2014-03-01 (EC3);
        SN-0006's subcategory id is "n/a" (EC5)                                     build
    L4  subcategories only: 1 renamed Mountain, 4 renamed Brackets, at 2014-04-01  build
    L5  products only: SN-0003 back in 2 at 2014-05-01 (EC4)                       build
        no new files                                                     build --full-refresh

The products' loads have ``harness.load_id(n)``; the subcategories' land half an hour before
them, as their own resource's loads. ``on_sale_per_subcategory`` answers the business question
from these rows alone, without dbt.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from itertools import pairwise

import pytest
import replay
from harness import (
    SUBCATEGORIES,
    Snapshot,
    Workspace,
    attribute,
    load_id,
    naive_utc,
    posit,
    product,
    q,
    subcategory,
    tail,
    write_load,
)

TIE = "PR_in_PS_contains"
TIE_POSIT, TIE_ANNEX = f"{TIE}_Posit", f"{TIE}_Annex"
PRODUCT_ROLE, SUBCATEGORY_ROLE = "PR_ID_in", "PS_ID_contains"
SID = "PS_SID_ProductSubcategory_SourceId"

D0, MOVE, RENAME, RESTORE = "2014-02-08", "2014-03-01", "2014-04-01", "2014-05-01"
NAMES = {1: "Mountain Bikes", 2: "Road Bikes", 3: "Touring Bikes", 4: "Bottom Brackets"}
RENAMED = {1: "Mountain", 4: "Brackets"}
LABELS = ("L1", "L2", "L3", "L4", "L5", "full")


def subcategory_load_id(n: int) -> str:
    """The n-th subcategories load: half an hour before the n-th products load."""
    return f"{1717000000 + 3600 * n - 1800}.25"


def _subcategories(ids, renamed: bool = False) -> list[dict]:
    rows = []
    for i in ids:
        if renamed and i in RENAMED:
            rows.append(subcategory(i, RENAMED[i], modified=RENAME))
        else:
            rows.append(subcategory(i, NAMES[i]))
    return rows


def _first_products() -> dict[str, dict]:
    return {
        "SN-0001": product(1, "SN-0001", "Mountain One", subcategory=1, modified=D0),
        "SN-0002": product(2, "SN-0002", "No Subcategory", subcategory=None, sell_end="2013-12-31", modified=D0),
        "SN-0003": product(3, "SN-0003", "Road Three", subcategory=2, modified=D0),
        "SN-0004": product(4, "SN-0004", "Touring Four", subcategory=3, modified=D0),
        "SN-0005": product(5, "SN-0005", "Mountain Five", subcategory=1, modified=D0),
        "SN-0006": product(6, "SN-0006", "Road Six", subcategory=2, modified=D0),
    }


def _third_products() -> dict[str, dict]:
    rows = _first_products()
    rows["SN-0001"].update(Name="Road One", ProductSubcategoryId=2, ModifiedDate=MOVE)
    rows["SN-0003"].update(ProductSubcategoryId=None, ModifiedDate=MOVE)
    rows["SN-0005"].update(ModifiedDate=MOVE)
    rows["SN-0006"].update(ProductSubcategoryId="n/a")
    return rows


def _fifth_products() -> dict[str, dict]:
    rows = _third_products()
    rows["SN-0003"].update(ProductSubcategoryId=2, ModifiedDate=RESTORE)
    return rows


PRODUCT_LOADS: dict[int, list[dict]] = {
    1: list(_first_products().values()),
    2: list(_first_products().values()),
    3: list(_third_products().values()),
    5: list(_fifth_products().values()),
}
SUBCATEGORY_LOADS: dict[int, list[dict]] = {
    1: _subcategories((1, 2, 4)),
    2: _subcategories((1, 2, 3, 4)),
    3: _subcategories((1, 2, 3, 4)),
    4: _subcategories((1, 2, 3, 4), renamed=True),
}


class Story:
    """The workspace, a snapshot per good build, and the first failure."""

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

    def snap(self, label: str) -> Snapshot:
        if label not in self.snaps:
            pytest.fail(f"story #6's lake never reached {label}: {self.failure}")
        return self.snaps[label]


def land(ws: Workspace, n: int) -> None:
    if n in SUBCATEGORY_LOADS:
        write_load(ws.lake, subcategory_load_id(n), SUBCATEGORY_LOADS[n], resource=SUBCATEGORIES)
    if n in PRODUCT_LOADS:
        write_load(ws.lake, load_id(n), PRODUCT_LOADS[n])


def run(ws: Workspace) -> Story:
    """Land and build L1 to L5, then a full refresh; stops at the first failure."""
    story = Story(ws)
    land(ws, 1)
    if not (story.ok(ws.generate(), "task generate") and story.build("L1")):
        return story
    for n in (2, 3, 4, 5):
        land(ws, n)
        if not story.build(f"L{n}"):
            return story
    story.build("full", "--full-refresh")
    return story


# --------------------------------------------------------------------------- reading integrate


def numbers(snap: Snapshot) -> dict:
    """PR_ID -> ProductNumber."""
    return dict(snap.sql(f"select distinct PR_NUM_PR_ID, {q(attribute('NUM'))} from integrate.{q(posit('NUM'))}"))


def source_ids(snap: Snapshot) -> dict:
    """PS_ID -> the subcategory's source id (ProductSubcategoryId), from its key attribute."""
    names = snap.relations("integrate")
    assert f"{SID}_Posit" in names, f"integrate has no {SID}_Posit: {sorted(names)}"
    return {k: int(v) for k, v in snap.sql(f"select distinct PS_SID_PS_ID, {q(SID)} from integrate.{q(SID + '_Posit')}")}


def tie_rows(snap: Snapshot, query: str) -> dict[str, int]:
    """ProductNumber -> subcategory source id of each tie row ``query`` returns with a subcategory."""
    by_number, by_source = numbers(snap), source_ids(snap)
    out: dict[str, int] = {}
    for product_id, subcategory_id in snap.sql(
        f"select {q(PRODUCT_ROLE)}, {q(SUBCATEGORY_ROLE)} from ({query}) where {q(SUBCATEGORY_ROLE)} is not null"
    ):
        number = by_number[product_id]
        assert number not in out, f"`{query}` relates {number} to two subcategories"
        out[number] = by_source[subcategory_id]
    return out


# --------------------------------------------------------------------------- reading serve


def subcategory_on(snap: Snapshot, pr_id, day: str) -> str | None:
    """The subcategory name a product reads through ``_bridge`` on ``day``: its one product-stage row
    valid then, joined to ``product_subcategory`` by its PIT key; None if the key joins no row."""
    rows = snap.sql(
        "select ps.product_subcategory__name, b._key__product_subcategory "
        "from serve__uss._bridge b "
        "left join serve__uss.product_subcategory ps on ps._key__product_subcategory = b._key__product_subcategory "
        "where b.stage = 'product' and split_part(b._key__product, '|', 1) = ? "
        f"and b._valid_from <= timestamp '{day}' and timestamp '{day}' < b._valid_to",
        [str(pr_id)],
    )
    assert len(rows) == 1, f"_bridge has {len(rows)} product rows of PR_ID {pr_id} valid on {day}: {rows}"
    return rows[0][0]


# --------------------------------------------------------------------------- the answer, from the rows


def _day(value) -> date | None:
    return None if value is None else date.fromisoformat(str(value)[:10])


def _moment(value: str) -> datetime:
    return datetime.fromisoformat(str(value)[:10])


def _subcategory_id(raw) -> tuple[int | None, bool]:
    """(value, cast failed) of a ProductSubcategoryId as the contract's integer cast reads it."""
    if raw is None:
        return None, False
    try:
        return int(str(raw)), False
    except ValueError:
        return None, True


def on_sale_per_subcategory(day: str, through: int) -> dict[str, int]:
    """Subcategory name -> products on sale on ``day`` after loads 1..``through``, from the rows alone.

    The tie is replayed as an attribute (ADR-0036) whose statements about a subcategory not landed by
    their load are skipped (ADR-0037), and read with serve's backfill (ADR-0039); a subcategory's name
    likewise. A product is on sale as #1 defines it, from its latest row."""
    target = date.fromisoformat(day)
    ties: dict[str, replay._Attribute] = defaultdict(replay._Attribute)
    names: dict[int, replay._Attribute] = defaultdict(replay._Attribute)
    known: set[int] = set()
    latest: dict[str, dict] = {}
    for n in range(1, through + 1):
        for row in SUBCATEGORY_LOADS.get(n, []):
            known.add(row["ProductSubcategoryId"])
            names[row["ProductSubcategoryId"]].apply(_moment(row["ModifiedDate"]), row["Name"], False)
        for row in sorted(PRODUCT_LOADS.get(n, []), key=lambda r: r["ModifiedDate"]):
            value, failed = _subcategory_id(row["ProductSubcategoryId"])
            latest[row["ProductNumber"]] = row
            if value is not None and value not in known:
                continue
            ties[row["ProductNumber"]].apply(_moment(row["ModifiedDate"]), value, failed)
    counts: dict[str, int] = defaultdict(int)
    for number, row in latest.items():
        start, end, gone = _day(row["SellStartDate"]), _day(row["SellEndDate"]), _day(row["DiscontinuedDate"])
        if start is None or start > target or (end is not None and end < target) or (gone is not None and gone <= target):
            continue
        held = ties[number].on(target)
        counts["[not available]" if held is None else names[held].on(target)] += 1
    return dict(counts)


# --------------------------------------------------------------------------- the split bridge's shape

FIRST, LAST = datetime(1, 1, 1), datetime(9999, 12, 31)
GHOST_KEYS = ("[not available]", "[not applicable]")
STAGED = "serve__uss_staging"


def _naive(value) -> datetime:
    if isinstance(value, datetime):
        return naive_utc(value)
    return datetime(value.year, value.month, value.day)


def split_bridge(snap: Snapshot) -> list[tuple]:
    """(PR_ID as text, _key__product, _key__product_subcategory, _valid_from, _valid_to) of every row of
    the staged bridge bridge__product, in identity and valid-from order; fails if it is not split by the tie."""
    columns = snap.columns(STAGED, "bridge__product")
    assert "_key__product_subcategory" in columns, (
        f"{STAGED}.bridge__product does not carry _key__product_subcategory: {columns}"
    )
    rows = snap.sql(
        "select split_part(_key__product, '|', 1), _key__product, _key__product_subcategory, _valid_from, _valid_to "
        f"from {STAGED}.bridge__product order by 1, 4"
    )
    return [(i, kp, ks, _naive(f), _naive(t)) for i, kp, ks, f, t in rows]


def tiling_problems(snap: Snapshot) -> list[str]:
    """Each product whose bridge__product intervals do not tile [0001-01-01, 9999-12-31) exactly once."""
    by_identity: dict[str, list[tuple]] = defaultdict(list)
    for identity, _, _, valid_from, valid_to in split_bridge(snap):
        by_identity[identity].append((valid_from, valid_to))
    identities = {str(r[0]) for r in snap.sql("select PR_ID from integrate.PR_Product")}
    problems = [f"PR_ID {i} has no bridge__product row" for i in sorted(identities - set(by_identity))]
    for identity, intervals in sorted(by_identity.items()):
        if intervals[0][0] != FIRST:
            problems.append(f"PR_ID {identity} starts at {intervals[0][0]}, not 0001-01-01")
        if intervals[-1][1] != LAST:
            problems.append(f"PR_ID {identity} ends at {intervals[-1][1]}, not 9999-12-31")
        for (f, t), (later_from, later_to) in pairwise(intervals):
            if t != later_from:
                problems.append(f"PR_ID {identity}: [{f}, {t}) then [{later_from}, {later_to}): a gap or an overlap")
        problems += [f"PR_ID {identity}: empty interval at {f}" for f, t in intervals if not f < t]
    return problems


def pit_key_problems(snap: Snapshot) -> list[str]:
    """Each bridge__product row whose PIT keys do not name versions valid over its whole interval."""
    split_bridge(snap)
    rows = snap.sql(
        "select b._key__product, b._key__product_subcategory, b._valid_from, b._valid_to, "
        "p._key__product, p.product__valid_from, p.product__valid_to, "
        "ps._key__product_subcategory, ps.product_subcategory__valid_from, ps.product_subcategory__valid_to "
        f"from {STAGED}.bridge__product b "
        "left join serve__uss.product p on p._key__product = b._key__product "
        "left join serve__uss.product_subcategory ps on ps._key__product_subcategory = b._key__product_subcategory"
    )
    problems = []
    for key, sub_key, f, t, p_key, p_from, p_to, ps_key, ps_from, ps_to in rows:
        f, t = _naive(f), _naive(t)
        if p_key is None or key in GHOST_KEYS:
            problems.append(f"[{f}, {t}) names product {key!r}, which serve__uss.product does not hold")
        elif not (_naive(p_from) <= f and t <= _naive(p_to)):
            problems.append(f"[{f}, {t}) names product {key}, valid [{p_from}, {p_to})")
        if sub_key is None or sub_key in GHOST_KEYS:
            continue
        if ps_key is None:
            problems.append(f"[{f}, {t}) of {key} names subcategory {sub_key!r}, which product_subcategory does not hold")
        elif not (_naive(ps_from) <= f and t <= _naive(ps_to)):
            problems.append(f"[{f}, {t}) of {key} names subcategory {sub_key}, valid [{ps_from}, {ps_to})")
    return problems
