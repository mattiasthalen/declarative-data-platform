"""The S1 test harness: a synthetic dlt lake, throwaway copies of the repo, and warehouse snapshots.

The tests hold the build to these interfaces, which the spec implies but does not spell out:

- The lake: ``$LAKE_ROOT/<resource>/date=YYYY-MM-DD/hour=HH/<load_id>.<file_id>.parquet``,
  one Parquet file per load, with the columns ``data`` (the source row as JSON text),
  ``_dlt_load_id`` and ``_dlt_id`` -- dlt's landed shape. ``tests/ingest`` holds ingest to
  writing exactly this; the end-to-end tests write it by hand.
- ``uv run task generate`` regenerates every layer; ``uv run dbt build --target dev`` builds
  into ``warehouse/dev.duckdb`` under the project root, reading the lake from ``LAKE_ROOT``.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RESOURCE = "adventure_works__products"
CONTRACT = "adventure_works__products"
# Contracts sit one folder per source, one file per resource (ADR-0017); the id stays CONTRACT.
CONTRACT_PATH = "contracts/adventure_works/products.yaml"

# Everything a fresh clone would not have.
NOT_IN_A_CLONE = shutil.ignore_patterns(
    ".git",
    ".venv",
    "target",
    "logs",
    "dbt_packages",
    "__pycache__",
    ".pytest_cache",
    "*.duckdb",
    "*.duckdb.wal",
    "lake",
    "dist",
)

SCHEMAS = ("raw", "conform", "integrate", "serve__uss_staging", "serve__uss")


# --------------------------------------------------------------------------- the lake


def write_load(lake_root: Path, load_id: str, rows: list[dict], resource: str = RESOURCE) -> Path:
    """Write one dlt load of ``rows`` in the landed shape and return the file written."""
    import duckdb

    landed = datetime.fromtimestamp(float(load_id), UTC)
    folder = lake_root / resource / f"date={landed:%Y-%m-%d}" / f"hour={landed:%H}"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{load_id}.{uuid.uuid4().hex[:10]}.parquet"
    con = duckdb.connect()
    try:
        con.execute("create table landed (data varchar, _dlt_load_id varchar, _dlt_id varchar)")
        con.executemany(
            "insert into landed values (?, ?, ?)",
            [(json.dumps(row), load_id, uuid.uuid4().hex[:14]) for row in rows],
        )
        con.execute(f"copy landed to '{path.as_posix()}' (format parquet)")
    finally:
        con.close()
    return path


def product(
    product_id: int,
    number: str,
    name: str,
    *,
    color: str | None = "Silver",
    line: str | None = "M",
    sell_start: str | None = "2011-05-31",
    sell_end: str | None = None,
    discontinued: str | None = None,
    modified: str | None = "2014-02-08",
    subcategory: int | None = 14,
    model: int | None = 19,
) -> dict:
    """An AdventureWorks Products row as the OData feed serves it.

    The live shape (docs/assumptions.md, Measured): PascalCase names with ``Id``, not ``ID``,
    and dates as plain ``YYYY-MM-DD``, ``ModifiedDate`` included.
    """
    return {
        "ProductId": product_id,
        "Name": name,
        "ProductNumber": number,
        "MakeFlag": True,
        "FinishedGoodsFlag": True,
        "Color": color,
        "SafetyStockLevel": 100,
        "ReorderPoint": 75,
        "StandardCost": 10.5,
        "ListPrice": 20.25,
        "Size": None,
        "SizeUnitMeasureCode": None,
        "WeightUnitMeasureCode": None,
        "Weight": None,
        "DaysToManufacture": 1,
        "ProductLine": line,
        "Class": None,
        "Style": None,
        "ProductSubcategoryId": subcategory,
        "ProductModelId": model,
        "SellStartDate": sell_start,
        "SellEndDate": sell_end,
        "DiscontinuedDate": discontinued,
        "Rowguid": str(uuid.UUID(int=product_id)),
        "ModifiedDate": modified,
    }


def load_id(n: int) -> str:
    """The n-th load's id: dlt's seconds-since-epoch string, an hour apart, at hour >= 10 UTC."""
    return f"{1717000000 + 3600 * n}.25"


def epoch_us(load: str) -> int:
    seconds, fraction = load.split(".")
    return int(seconds) * 1_000_000 + int(fraction.ljust(6, "0"))


# --------------------------------------------------------------------------- the database


def q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


@dataclass
class Snapshot:
    """A copy of the warehouse and dbt's artifacts as one build left them."""

    db: Path
    output: str
    run_results: dict | None
    manifest: dict | None

    def sql(self, query: str, params: list | None = None) -> list[tuple]:
        import duckdb

        con = duckdb.connect(str(self.db), read_only=True)
        try:
            return con.execute(query, params or []).fetchall()
        finally:
            con.close()

    def relations(self, schema: str) -> dict[str, str]:
        """name -> table_type of every relation in ``schema``."""
        return dict(
            self.sql(
                "select table_name, table_type from information_schema.tables where table_schema = ?",
                [schema],
            )
        )

    def columns(self, schema: str, relation: str) -> list[str]:
        return [
            r[0]
            for r in self.sql(
                "select column_name from information_schema.columns "
                "where table_schema = ? and table_name = ? order by ordinal_position",
                [schema, relation],
            )
        ]

    def count(self, schema: str, relation: str) -> int:
        return self.sql(f"select count(*) from {q(schema)}.{q(relation)}")[0][0]

    def counts(self, schemas: tuple[str, ...]) -> dict[str, int]:
        return {
            f"{schema}.{name}": self.count(schema, name)
            for schema in schemas
            for name in sorted(self.relations(schema))
        }

    # -- conform

    def staged(self) -> str:
        """The conform staged table for Products."""
        tables = [
            name
            for name, kind in self.relations("conform").items()
            if kind == "BASE TABLE" and "product" in name.lower()
        ]
        assert len(tables) == 1, f"expected one staged Products table in conform, found {tables}"
        return tables[0]

    # -- the load log

    def load_log(self) -> list[tuple[object, str]]:
        """(batch id, status) of every load-log row, in id order."""
        found = self.sql(
            "select table_schema, table_name from information_schema.tables "
            "where lower(table_name) like '%batch_log%' or lower(table_name) like '%load_log%'"
        )
        assert len(found) == 1, f"expected one load log (LOAD_BATCH_LOG pattern), found {found}"
        schema, table = found[0]
        cols = self.columns(schema, table)
        status = next(c for c in cols if "status" in c.lower())
        ident = next(
            (c for c in cols if c.lower() in ("batch_id", "load_batch_id", "batchid", "id")),
            None,
        ) or next(c for c in cols if c.lower().endswith("id"))
        return self.sql(f"select {q(ident)}, {q(status)} from {q(schema)}.{q(table)} order by 1")

    def metadata_values(self) -> set:
        """Every Metadata_* value written into an integrate table."""
        values: set = set()
        for name, kind in self.relations("integrate").items():
            if kind != "BASE TABLE":
                continue
            for col in self.columns("integrate", name):
                if col.startswith("Metadata_"):
                    values |= {r[0] for r in self.sql(f"select distinct {q(col)} from integrate.{q(name)}")}
        return values

    # -- dbt artifacts

    def results(self) -> list[dict]:
        assert self.run_results is not None, "dbt wrote no run_results.json"
        return self.run_results["results"]


@dataclass
class Step:
    name: str
    args: tuple[str, ...]
    returncode: int
    output: str


@dataclass
class Workspace:
    """A copy of the repo as a fresh clone has it, with its own lake and warehouse."""

    root: Path
    steps: list[Step] = field(default_factory=list)

    @property
    def lake(self) -> Path:
        return self.root / "lake"

    @property
    def warehouse(self) -> Path:
        return self.root / "warehouse" / "dev.duckdb"

    def env(self) -> dict[str, str]:
        env = {
            k: v
            for k, v in os.environ.items()
            if k not in ("VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT", "DBT_PROFILES_DIR", "LAKE_ROOT")
        }
        env.update(
            LAKE_ROOT=str(self.lake),
            DBT_SEND_ANONYMOUS_USAGE_STATS="false",
            DO_NOT_TRACK="1",
            UV_NO_PROGRESS="1",
        )
        return env

    def run(self, *args: str, name: str | None = None) -> Step:
        proc = subprocess.run(
            args, cwd=self.root, env=self.env(), capture_output=True, text=True, timeout=1800
        )
        step = Step(name or " ".join(args), args, proc.returncode, proc.stdout + proc.stderr)
        self.steps.append(step)
        return step

    def sync(self) -> Step:
        return self.run("uv", "sync")

    def generate(self) -> Step:
        return self.run("uv", "run", "task", "generate")

    def build(self, *select: str) -> Step:
        return self.run("uv", "run", "dbt", "build", "--target", "dev", *select)

    def write_load(self, n: int, rows: list[dict]) -> Path:
        return write_load(self.lake, load_id(n), rows)

    def snapshot(self, label: str, step: Step) -> Snapshot:
        """Copy the warehouse as ``step`` left it. The file keeps its name: views name its catalog."""
        folder = self.root.parent / f"{self.root.name}-snapshots" / label
        folder.mkdir(parents=True, exist_ok=True)
        for suffix in ("", ".wal"):
            source = Path(str(self.warehouse) + suffix)
            if source.exists():
                shutil.copy2(source, folder / source.name)

        def artifact(name: str) -> dict | None:
            path = self.root / "target" / name
            return json.loads(path.read_text()) if path.exists() else None

        return Snapshot(
            folder / "dev.duckdb", step.output, artifact("run_results.json"), artifact("manifest.json")
        )

    def tree(self) -> dict[str, str]:
        """relative path -> sha256 of every file a generator could touch."""
        skip = {".venv", "target", "logs", "lake", "warehouse", "dbt_packages", ".git", "__pycache__"}
        out = {}
        for path in sorted(self.root.rglob("*")):
            rel = path.relative_to(self.root)
            if rel.parts[0] in skip or "__pycache__" in rel.parts or not path.is_file():
                continue
            out[rel.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
        return out


def tail(text: str, limit: int = 6000) -> str:
    return text if len(text) <= limit else "...\n" + text[-limit:]


def require(step: Step) -> Step:
    assert step.returncode == 0, f"`{step.name}` exited {step.returncode}:\n{tail(step.output)}"
    return step


SNAKE = re.compile(r"^_?[a-z][a-z0-9_]*$")


# --------------------------------------------------------------------------- Anchor names

# Roenbaeck's default naming for PR_Product: mnemonic -> attribute descriptor.
ATTRIBUTES = {
    "NUM": "ProductNumber",
    "NAM": "Name",
    "LIN": "ProductLine",
    "COL": "Color",
    "SST": "SellStart",
    "SEN": "SellEnd",
    "DIS": "Discontinued",
}


def attribute(mnemonic: str) -> str:
    """The assembled attribute's name, e.g. ``PR_COL_Product_Color``; also its value column."""
    return f"PR_{mnemonic}_Product_{ATTRIBUTES[mnemonic]}"


def posit(mnemonic: str) -> str:
    return attribute(mnemonic) + "_Posit"


def annex(mnemonic: str) -> str:
    return attribute(mnemonic) + "_Annex"


def pr_id(snap: Snapshot, number: str):
    """The one PR_ID posited for ``number``."""
    ids = snap.sql(
        f"select distinct PR_NUM_PR_ID from integrate.{q(posit('NUM'))} where {q(attribute('NUM'))} = ?",
        [number],
    )
    assert len(ids) == 1, f"product {number} has PR_IDs {ids}, expected exactly one"
    return ids[0][0]


def posits(snap: Snapshot, mnemonic: str, identity) -> list[tuple]:
    """(posit id, value as text, ChangedAt as date text) of one product's posits, in id order."""
    m = mnemonic
    return snap.sql(
        f"select PR_{m}_ID, cast({q(attribute(m))} as varchar), cast(cast(PR_{m}_ChangedAt as date) as varchar) "
        f"from integrate.{q(posit(m))} where PR_{m}_PR_ID = ? order by PR_{m}_ID",
        [identity],
    )


def annexes(snap: Snapshot, mnemonic: str, identity) -> list[tuple]:
    """(posit id, PositedAt in epoch microseconds, Positor, Reliability) of one product's annex rows."""
    m = mnemonic
    return snap.sql(
        f"select a.PR_{m}_ID, epoch_us(a.PR_{m}_PositedAt), a.PR_{m}_Positor, a.PR_{m}_Reliability "
        f"from integrate.{q(annex(m))} a join integrate.{q(posit(m))} p on p.PR_{m}_ID = a.PR_{m}_ID "
        f"where p.PR_{m}_PR_ID = ? order by 1, 2, 4",
        [identity],
    )


def latest(snap: Snapshot, number: str, mnemonic: str):
    """The value ``lPR_Product`` shows for ``number``'s attribute, as text."""
    rows = snap.sql(
        f"select cast({q(attribute(mnemonic))} as varchar) from integrate.lPR_Product where PR_ID = ?",
        [pr_id(snap, number)],
    )
    assert len(rows) == 1, f"lPR_Product has {len(rows)} rows for {number}"
    return rows[0][0]


# --------------------------------------------------------------------------- the point-in-time perspective

# A DuckDB table macro, not a relation: information_schema does not list it, so its shape is read
# with DESCRIBE over a call.
PIT = 'integrate."pPR_Product"'


def at(moment: str) -> str:
    """A timestamp literal for a pPR call: ``at("2014-03-01")``, ``at("2014-02-28 23:59:59")``."""
    return f"timestamp '{moment}'"


def pit_columns(snap: Snapshot, when: str) -> list[str]:
    """pPR's column names, in order, for a call with the SQL expression ``when``."""
    return [r[0] for r in snap.sql(f"describe select * from {PIT}({when})")]


def pit(snap: Snapshot, when: str) -> dict:
    """PR_ID -> {column: value} of every row pPR returns for the SQL expression ``when``."""
    columns = pit_columns(snap, when)
    rows = snap.sql(f"select * from {PIT}({when})")
    out = {}
    for row in rows:
        record = dict(zip(columns, row))
        assert record["PR_ID"] not in out, f"pPR({when}) returns PR_ID {record['PR_ID']} twice"
        out[record["PR_ID"]] = record
    return out


# --------------------------------------------------------------------------- the USS

GHOSTS = ("[not available]", "[not applicable]")

_DIMENSION_COLUMNS = {
    "number": ("product__product_number", "product__number"),
    "name": ("product__name",),
    "line": ("product__product_line", "product__line"),
    "color": ("product__color", "product__colour"),
    "sell_start": ("product__sell_start", "product__sell_start_date"),
    "sell_end": ("product__sell_end", "product__sell_end_date"),
    "discontinued": ("product__discontinued", "product__discontinued_date"),
}


def dimension_column(snap: Snapshot, what: str) -> str:
    columns = snap.columns("serve__uss", "product")
    for candidate in _DIMENSION_COLUMNS[what]:
        if candidate in columns:
            return candidate
    raise AssertionError(f"serve__uss.product has no {what} column among {columns}")


def ghost_rows(snap: Snapshot) -> dict[str, int]:
    """How many dimension rows carry each ghost marker in any text column."""
    text = [
        r[0]
        for r in snap.sql(
            "select column_name from information_schema.columns where table_schema = 'serve__uss' "
            "and table_name = 'product' and data_type = 'VARCHAR'"
        )
    ]
    found = {}
    for ghost in GHOSTS:
        where = " or ".join(f"{q(c)} = ?" for c in text)
        found[ghost] = snap.sql(
            f"select count(*) from serve__uss.product where {where}", [ghost] * len(text)
        )[0][0]
    return found


def integrity_violations(snap: Snapshot) -> int:
    names = [n for n in snap.relations("integrate") if n.lower().replace("_", "") == "integrityviolations"]
    assert len(names) == 1, (
        f"integrate has no IntegrityViolations relation: {sorted(snap.relations('integrate'))}"
    )
    return snap.count("integrate", names[0])
