"""Generate the serve dbt models: a Unified Star Schema on business time (ADR-0011).

Reads the Anchor model and writes two packages: ``models/serve/uss_staging/``, one staged bridge
per anchor (``bridge__<entity>``), and ``models/serve/uss/``, one dimension per anchor
(``<entity>``, one row per version and two ghost rows) and ``_bridge``, the union by name of the
staged bridges. Serve models written by hand live in folders without a generator's README.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import yaml

import integrate
import ownership

GENERATOR = "serve"
STAGING = Path("models") / "serve" / "uss_staging"
USS = Path("models") / "serve" / "uss"
NOT_AVAILABLE = "[not available]"
NOT_APPLICABLE = "[not applicable]"


def snake(descriptor: str) -> str:
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", "_", descriptor).lower()


def entity_literal(anchor, attributes) -> str:
    """The anchor and each attribute with its dimension column, as a Jinja dict literal."""
    entity = snake(anchor.descriptor)
    attrs = ", ".join(
        f"{{'prefix': '{t.prefix}', 'name': '{t.name}', 'column': '{entity}__{snake(t.descriptor)}'}}"
        for t in attributes
    )
    return (
        f"{{'entity': '{entity}', 'anchor': '{anchor.name}', 'anchor_mnemonic': '{anchor.mnemonic}', "
        f"'attributes': [{attrs}]}}"
    )


def header(anchor, attributes) -> str:
    """The config, with the hook that forgets the versions of identities this build changed."""
    e = entity_literal(anchor, attributes)
    return (
        f"{{{{ config(materialized='incremental', pre_hook=\"{{{{ uss_forget({e}) }}}}\") }}}}\n"
        f"{{% set e = {e} %}}\n"
    )


def staged_bridge(anchor, attributes) -> str:
    entity = snake(anchor.descriptor)
    return (
        f"-- The staged bridge of {entity}: one row per version, keyed like the dimension.\n"
        + header(anchor, attributes)
        + "with {{ uss_versions(e) }}\n"
        "select\n"
        f"    '{entity}' as stage,\n"
        f"    coalesce(_key, '{NOT_AVAILABLE}') as _key__{entity},\n"
        "    valid_from as _valid_from,\n"
        "    valid_to as _valid_to\n"
        "from versions\n"
    )


def dimension(anchor, attributes) -> str:
    entity = snake(anchor.descriptor)
    columns = [f"    v._key as _key__{entity}", f"    v.valid_from as {entity}__valid_from", f"    v.valid_to as {entity}__valid_to"]
    ghosts = {NOT_AVAILABLE: [], NOT_APPLICABLE: []}
    for t in attributes:
        column = f"{entity}__{snake(t.descriptor)}"
        columns.append(f'    cast({t.prefix.lower()}.value as {t.data_range}) as {column}')
        text = t.data_range.lower().startswith(("varchar", "text", "string"))
        for ghost in ghosts:
            ghosts[ghost].append(f"'{ghost}'" if text else f"cast(null as {t.data_range})")
    joins = "\n".join(
        f"asof left join {t.prefix.lower()} on {t.prefix.lower()}.id = v.id and {t.prefix.lower()}.changed_at <= v.valid_from"
        for t in attributes
    )
    ghost_rows = "\n".join(
        f"union all\nselect '{ghost}', cast('0001-01-01' as timestamp), cast('9999-12-31' as timestamp), "
        + ", ".join(values)
        for ghost, values in ghosts.items()
    )
    return (
        f"-- The {entity} dimension: one row per version on business time, from an opening version at\n"
        f"-- 0001-01-01, plus the ghost rows {NOT_AVAILABLE} and {NOT_APPLICABLE}.\n"
        + header(anchor, attributes)
        + "with {{ uss_versions(e) }}\n"
        "select\n" + ",\n".join(columns) + "\nfrom versions v\n" + joins + "\n"
        "{% if not is_incremental() %}\n" + ghost_rows + "\n{% endif %}\n"
    )


def bridge(entities: list[str]) -> str:
    keys = ",\n".join(f"    coalesce(_key__{e}, '{NOT_APPLICABLE}') as _key__{e}" for e in entities)
    stages = "\n    union all by name\n".join(f"    select * from {{{{ ref('bridge__{e}') }}}}" for e in entities)
    return (
        "-- The bridge: every staged bridge unioned by name. A key a stage lacks is not applicable.\n"
        "{{ config(materialized='view') }}\n"
        "select\n    stage,\n" + keys + ",\n    _valid_from,\n    _valid_to\nfrom (\n" + stages + "\n)\n"
    )


def packages(root: Path) -> dict[Path, dict[str, str]]:
    _, anchors = integrate.read(root)
    staging: dict[str, str] = {}
    uss: dict[str, str] = {}
    models_staging, models_uss = [], []
    entities = []
    for anchor, attributes, _ in anchors:
        entity = snake(anchor.descriptor)
        entities.append(entity)
        staging[f"bridge__{entity}.sql"] = staged_bridge(anchor, attributes)
        uss[f"{entity}.sql"] = dimension(anchor, attributes)
        models_staging.append(
            {
                "name": f"bridge__{entity}",
                "description": f"The staged bridge of {entity}: its own keys, one row per version.",
                "columns": [{"name": f"_key__{entity}", "data_tests": ["not_null", "unique"]}],
            }
        )
        models_uss.append(
            {
                "name": entity,
                "description": anchor.description,
                "columns": [
                    {
                        "name": f"_key__{entity}",
                        "description": "The identity and the version's valid-from, as identity|valid_from.",
                        "data_tests": ["not_null", "unique", "ghost_rows"],
                    }
                ]
                + [{"name": f"{entity}__{snake(t.descriptor)}", "description": t.description} for t in attributes],
            }
        )
    uss["_bridge.sql"] = bridge(entities)
    models_uss.append(
        {
            "name": "_bridge",
            "description": "The Puppini bridge: the union by name of every staged bridge.",
            "columns": [
                {
                    "name": f"_key__{e}",
                    "data_tests": [
                        "not_null",
                        {"relationships": {"arguments": {"to": f"ref('{e}')", "field": f"_key__{e}"}}},
                    ],
                }
                for e in entities
            ],
        }
    )
    dump = lambda models: yaml.safe_dump({"version": 2, "models": models}, sort_keys=False, width=100)  # noqa: E731
    staging["uss_staging.yml"] = dump(models_staging)
    uss["uss.yml"] = dump(models_uss)
    return {STAGING: staging, USS: uss}


def generate() -> int:
    try:
        planned = packages(Path.cwd())
    except (integrate.ModelError, KeyError) as error:
        print(f"{integrate.MODEL}: {error}")
        return 1
    return ownership.run(GENERATOR, f"{integrate.MODEL}", planned)


def main() -> int:
    parser = argparse.ArgumentParser(prog=GENERATOR, description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["generate"])
    parser.parse_args()
    return generate()
