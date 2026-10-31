"""Generate the raw and conform dbt models from the ODCS v3 data contracts in contracts/.

Per contract, a ``raw`` view reads the lake files of its resource, and a ``conform`` staged
model appends every load newer than its newest (ADR-0009): each property extracted from the
landed JSON by its physical name, rewritten by its ``transformLogic``, cast with ``try_cast``
(ADR-0010), and named in snake_case beside the ``_dlt__`` platform columns (ADR-0002).
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import yaml

import ownership

GENERATOR = "conform"
CONTRACTS = Path("contracts")

# ODCS logical type -> DuckDB type. A string needs no cast.
TYPES = {
    "string": None,
    "integer": "bigint",
    "number": "double",
    "boolean": "boolean",
    "date": "date",
    "timestamp": "timestamp",
}

SNAKE = re.compile(r"^[a-z][a-z0-9_]*$")
# A physical name is a JSON path into the landed row: names joined by dots.
PATH = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")
# The generated models are Jinja: no declared text may open a Jinja block.
JINJA = re.compile(r"\{[{%#]|[}%#]\}")
# What a transformLogic may call: functions of one text value, and nothing that reads or writes.
FUNCTIONS = frozenset(
    {"trim", "ltrim", "rtrim", "upper", "lower", "replace", "regexp_replace", "nullif", "coalesce",
     "substring", "left", "right", "concat", "lpad", "rpad", "strip_accents"}
)
KEYWORDS = frozenset({"value", "case", "when", "then", "else", "end", "null", "and", "or", "not", "is", "in", "like"})


class ContractError(Exception):
    pass


def q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def literal(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def texts(node) -> list[str]:
    """Every string in a parsed YAML document."""
    if isinstance(node, dict):
        return [t for k, v in node.items() for t in texts(k) + texts(v)]
    if isinstance(node, list):
        return [t for v in node for t in texts(v)]
    return [node] if isinstance(node, str) else []


def load(path: Path) -> dict:
    contract = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(contract, dict) or contract.get("kind") != "DataContract":
        raise ContractError(f"{path} is not an ODCS data contract")
    for text in texts(contract):
        if JINJA.search(text):
            raise ContractError(f"{path}: {text!r} holds a Jinja delimiter")
    objects = contract.get("schema") or []
    if len(objects) != 1:
        raise ContractError(f"{path} must declare exactly one schema object")
    for field in ("name", "physicalName"):
        if field in objects[0] and not SNAKE.match(str(objects[0][field])):
            raise ContractError(f"{path}: object {field} {objects[0][field]!r} is not snake_case")
    for prop in objects[0].get("properties") or []:
        name, logical = prop.get("name", ""), prop.get("logicalType")
        if not SNAKE.match(name):
            raise ContractError(f"{path}: property {name!r} is not snake_case")
        if logical not in TYPES:
            raise ContractError(f"{path}: {name} has unknown logicalType {logical!r}")
        if not PATH.match(str(prop.get("physicalName") or "")):
            raise ContractError(f"{path}: {name} needs a physicalName naming a JSON path")
    return contract


def value_expression(prop: dict) -> str:
    """The property's source text: the JSON value, rewritten by its transformLogic."""
    value = f"json_extract_string(data, {literal('$.' + prop['physicalName'])})"
    logic = prop.get("transformLogic")
    if not logic:
        return value
    unquoted = re.sub(r"'(?:[^']|'')*'", "''", logic)
    words = [(w.group(0).lower(), w.group(1)) for w in re.finditer(r"[A-Za-z_][A-Za-z0-9_]*(?=\s*(\()?)", unquoted)]
    if ";" in unquoted or any(not (name in FUNCTIONS if call else name in KEYWORDS) for name, call in words):
        raise ContractError(
            f"transformLogic of {prop['name']} may only rewrite its own value with "
            f"{', '.join(sorted(FUNCTIONS))}: {logic}"
        )
    return re.sub(r"\bvalue\b", value, logic)


def raw_model(name: str, resource: str) -> str:
    return (
        f"{{{{ config(alias={literal(name)}) }}}}\n"
        f"-- The landed files of {resource}: the row as JSON (data) beside dlt's columns.\n"
        f"{{{{ read_lake({literal(resource)}) }}}}\n"
    )


def staged_model(name: str, raw: str, properties: list[dict]) -> str:
    texts = ",\n".join(f"        {value_expression(p)} as {q(p['name'])}" for p in properties)

    typed = []
    failures = []
    for p in properties:
        cast = TYPES[p["logicalType"]]
        column = q(p["name"])
        if cast is None:
            typed.append(f"        {column}")
        else:
            typed.append(f"        try_cast({column} as {cast}) as {column}")
            failures.append(
                f"            case when {column} is not null and try_cast({column} as {cast}) is null "
                f"then {literal(p['name'])} end"
            )
    cast_failed = (
        "        list_filter([\n" + ",\n".join(failures) + "\n        ], lambda p: p is not null)"
        if failures
        else "        []::varchar[]"
    )
    load_number = "cast(_dlt_load_id as decimal(38, 9))"
    return f"""{{{{ config(materialized='incremental') }}}}
-- {name}: every load of the lake, appended whole when it is newer than the newest staged.
with landed as (
    select * from {{{{ ref({literal(raw)}) }}}}
    {{% if is_incremental() %}}
    where {load_number} > (
        select coalesce(max(cast(_dlt__load_id as decimal(38, 9))), 0) from {{{{ this }}}}
    )
    {{% endif %}}
),

source_text as (
    select
{texts},
        _dlt_load_id,
        _dlt_id,
        filename,
        "date",
        "hour"
    from landed
)

select
{",\n".join(typed)},
{cast_failed} as _contract__cast_failed,
        _dlt_load_id as _dlt__load_id,
        _dlt_id as _dlt__id,
        make_timestamp(cast(round({load_number} * 1000000) as bigint)) as _dlt__extracted_at,
        cast("date" as date) as _dlt__extracted_on,
        cast("hour" as integer) as _dlt__extracted_hour,
        filename as _dlt__file_name
from source_text
"""


def schema_file(name: str, contract: dict, properties: list[dict]) -> str:
    columns = []
    for p in properties:
        column = {"name": p["name"], "description": p.get("description", "")}
        tests = []
        if TYPES[p["logicalType"]] is not None:
            tests.append({"cast_failed": {"config": {"severity": "warn"}}})
        if p.get("required"):
            tests.append({"not_null": {"config": {"severity": "warn"}}})
        if tests:
            column["data_tests"] = tests
        columns.append(column)
    columns.append(
        {
            "name": "_contract__cast_failed",
            "description": "The properties whose non-null source value failed its cast in this row.",
        }
    )
    document = {
        "version": 2,
        "models": [
            {
                "name": name,
                "description": (contract.get("schema")[0].get("description") or "").strip(),
                "columns": columns,
            }
        ],
    }
    return yaml.safe_dump(document, sort_keys=False, allow_unicode=True, width=100)


def packages(root: Path) -> dict[Path, dict[str, str]]:
    out: dict[Path, dict[str, str]] = {}
    for path in sorted((root / CONTRACTS).glob("*.yaml")):
        contract = load(path)
        domain = contract.get("domain")
        if not domain or not SNAKE.match(domain):
            raise ContractError(f"{path}: domain must name the source in snake_case")
        obj = contract["schema"][0]
        name = obj["name"]
        resource = obj.get("physicalName") or name
        properties = obj.get("properties") or []
        raw = f"raw__{name}"
        out.setdefault(Path("models") / "raw" / domain, {})[f"{raw}.sql"] = raw_model(name, resource)
        conform = out.setdefault(Path("models") / "conform" / domain, {})
        conform[f"{name}.sql"] = staged_model(name, raw, properties)
        conform[f"{name}.yml"] = schema_file(name, contract, properties)
    return out


def generate() -> int:
    try:
        planned = packages(Path.cwd())
    except ContractError as error:
        print(error)
        return 1
    return ownership.run(GENERATOR, "the data contracts in contracts/", planned)


def main() -> int:
    parser = argparse.ArgumentParser(prog=GENERATOR, description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["generate"])
    parser.parse_args()
    return generate()
