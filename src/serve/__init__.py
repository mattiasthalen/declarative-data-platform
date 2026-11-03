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

import erd
import integrate
import ownership

GENERATOR = "serve"
STAGING = Path("models") / "serve" / "uss_staging"
USS = Path("models") / "serve" / "uss"
NOT_AVAILABLE = "[not available]"
NOT_APPLICABLE = "[not applicable]"


def snake(descriptor: str) -> str:
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", "_", descriptor).lower()


def followed(anchor, tied) -> list:
    """The ties a staged bridge follows from ``anchor``: those whose only identifier role is its, to
    another anchor (ADR-0038). Self-ties are not followed."""
    return [t for t in tied if t.owner.mnemonic == anchor.mnemonic and t.other.mnemonic != anchor.mnemonic]


def entity_literal(anchor, attributes, model) -> str:
    """The anchor, each attribute and each followed tie with the entity it reaches, as a Jinja dict
    literal; ``model`` maps a mnemonic to its (anchor, attributes) and ties."""
    entity = snake(anchor.descriptor)
    attrs = ", ".join(f"{{'prefix': '{t.prefix}', 'name': '{t.name}'}}" for t in attributes)
    anchors, tied = model
    ties = ", ".join(
        f"{{'name': '{t.name}', 'identity_column': '{t.identity_column}', 'value_column': '{t.value_column}', "
        f"'reaches': {entity_literal(*anchors[t.other.mnemonic], model)}}}"
        for t in followed(anchor, tied)
    )
    return (
        f"{{'entity': '{entity}', 'anchor': '{anchor.name}', 'anchor_mnemonic': '{anchor.mnemonic}', "
        f"'attributes': [{attrs}], 'ties': [{ties}]}}"
    )


def keys(anchor, model, path=()) -> list[str]:
    """The entities whose PIT keys ``anchor``'s staged bridge carries: its own, then each followed tie's
    reached stage's, in order. A key reached twice, or ties that lead back to ``anchor``, are refused."""
    anchors, tied = model
    if anchor.mnemonic in path:
        raise integrate.ModelError(f"the ties followed from {anchor.name} lead back to it; a cycle of ties is not supported")
    found = [snake(anchor.descriptor)]
    for t in followed(anchor, tied):
        for key in keys(anchors[t.other.mnemonic][0], model, (*path, anchor.mnemonic)):
            if key in found:
                raise integrate.ModelError(f"{anchor.name} reaches {key} twice; only one path to an entity is supported")
            found.append(key)
    return found


def reached_models(anchor, model) -> list[str]:
    """The integrate models an incremental build reads to find what changed beyond ``anchor``: each
    followed tie and, recursively, the anchor and attributes it reaches. dbt cannot see these refs,
    which run only when the model is incremental, so the header declares them."""
    anchors, tied = model
    names = []
    for t in followed(anchor, tied):
        other, attributes = anchors[t.other.mnemonic]
        names += [t.name, other.name, *(a.name for a in attributes), *reached_models(other, model)]
    return names


def header(anchor, attributes, model) -> str:
    """The config, with the hook that forgets the versions of identities this build changed."""
    e = entity_literal(anchor, attributes, model)
    depends = "".join(f"-- depends_on: {{{{ ref('{name}') }}}}\n" for name in reached_models(anchor, model))
    return (
        f"{{{{ config(materialized='incremental', on_schema_change='fail', pre_hook=\"{{{{ uss_forget({e}) }}}}\") }}}}\n"
        + depends
        + f"{{% set e = {e} %}}\n"
    )


def staged_bridge(anchor, attributes, model) -> str:
    entity = snake(anchor.descriptor)
    ties = followed(anchor, model[1])
    if not ties:
        return (
            f"-- The staged bridge of {entity}: one row per version, keyed like the dimension.\n"
            + header(anchor, attributes, model)
            + "with {{ uss_versions(e) }}\n"
            "select\n"
            f"    '{entity}' as stage,\n"
            f"    _key as _key__{entity},\n"
            "    valid_from as _valid_from,\n"
            "    valid_to as _valid_to\n"
            "from versions\n"
        )
    anchors = model[0]
    columns = [f"    '{entity}' as stage", f"    v._key as _key__{entity}"]
    joins = ["asof left join versions v on v.id = s.id and v.valid_from <= s.valid_from"]
    for n, t in enumerate(ties, 1):
        for key in keys(anchors[t.other.mnemonic][0], model):
            columns.append(f"    coalesce(r{n}._key__{key}, '{NOT_AVAILABLE}') as _key__{key}")
        joins.append(f"asof left join reach_{n} r{n} on r{n}.id = s.id and r{n}.valid_from <= s.valid_from")
    columns += ["    s.valid_from as _valid_from", "    s.valid_to as _valid_to"]
    reaches = ",\n".join(
        f"reach_{n} as (\n    {{{{ uss_reach(e.ties[{n - 1}], '{snake(t.other.descriptor)}', "
        f"{keys(anchors[t.other.mnemonic][0], model)}) }}}}\n)"
        for n, t in enumerate(ties, 1)
    )
    splits = "\n    union\n".join(
        ["    select id, valid_from from versions"] + [f"    select id, valid_from from reach_{n}" for n in range(1, len(ties) + 1)]
    )
    return (
        f"-- The staged bridge of {entity}: one row per interval over which neither a version of {entity} nor\n"
        "-- what it reaches over its to-one ties changes, with the PIT key of each version valid for the\n"
        f"-- whole interval; {NOT_AVAILABLE} where a tie has no version (ADR-0038, ADR-0039).\n"
        + header(anchor, attributes, model)
        + "with {{ uss_versions(e) }},\n"
        + reaches
        + ",\n\nsplits as (\n"
        + splits
        + "\n),\n\nspans as (\n    select id, valid_from,\n"
        "        lead(valid_from, 1, cast('9999-12-31' as timestamp)) over (partition by id order by valid_from) as valid_to\n"
        "    from splits\n)\n\n"
        "select\n" + ",\n".join(columns) + "\nfrom spans s\n" + "\n".join(joins) + "\n"
    )


def dimension(anchor, attributes, model) -> str:
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
        f"-- The {entity} dimension: one row per version on business time, the first from 0001-01-01,\n"
        f"-- plus the ghost rows {NOT_AVAILABLE} and {NOT_APPLICABLE}.\n"
        + header(anchor, attributes, model)
        + "with {{ uss_versions(e) }}\n"
        "select\n" + ",\n".join(columns) + "\nfrom versions v\n" + joins + "\n"
        "{% if not is_incremental() %}\n" + ghost_rows + "\n{% endif %}\n"
    )


def bridge(entities: list[str]) -> str:
    columns = ",\n".join(f"    coalesce(_key__{e}, '{NOT_APPLICABLE}') as _key__{e}" for e in entities)
    stages = "\n    union all by name\n".join(f"    select * from {{{{ ref('bridge__{e}') }}}}" for e in entities)
    return (
        "-- The bridge: every staged bridge unioned by name. A key a stage lacks is not applicable.\n"
        "{{ config(materialized='view') }}\n"
        "select\n    stage,\n" + columns + ",\n    _valid_from,\n    _valid_to\nfrom (\n" + stages + "\n)\n"
    )


def diagram(anchors) -> str:
    """Each dimension, then the bridge, many to one to each dimension by its key."""
    entities, relationships = [], []
    for anchor, attributes, _ in anchors:
        entity = snake(anchor.descriptor)
        entities.append(
            (
                entity,
                [
                    erd.row("varchar", f"_key__{entity}", "PK"),
                    erd.row("timestamp", f"{entity}__valid_from"),
                    erd.row("timestamp", f"{entity}__valid_to"),
                ]
                + [erd.row(t.data_range, f"{entity}__{snake(t.descriptor)}") for t in attributes],
            )
        )
        relationships.append(f'_bridge }}o--|| {entity} : "_key__{entity}"')
    bridge_rows = (
        [erd.row("varchar", "stage")]
        + [erd.row("varchar", f"_key__{name}", "FK") for name, _ in entities]
        + [erd.row("timestamp", "_valid_from"), erd.row("timestamp", "_valid_to")]
    )
    return erd.diagram(entities + [("_bridge", bridge_rows)], relationships)


def bridge_key_tests(entity: str, *, warn: bool) -> list:
    """A key of the bridge must name a row of its dimension; a key inherited over a relationship only
    warns when it does not (story #6, [12])."""
    relationship = {"relationships": {"arguments": {"to": f"ref('{entity}')", "field": f"_key__{entity}"}}}
    if not warn:
        return ["not_null", relationship]
    return [
        {"not_null": {"config": {"severity": "warn"}}},
        {"relationships": relationship["relationships"] | {"config": {"severity": "warn"}}},
    ]


def packages(anchors, tied) -> dict[Path, dict[str, str]]:
    staging: dict[str, str] = {}
    uss: dict[str, str] = {}
    models_staging, models_uss = [], []
    entities = []
    model = ({anchor.mnemonic: (anchor, attributes) for anchor, attributes, _ in anchors}, list(tied))
    inherited: set[str] = set()
    for anchor, attributes, _ in anchors:
        entity = snake(anchor.descriptor)
        entities.append(entity)
        reached = keys(anchor, model)[1:]
        inherited |= set(reached)
        staging[f"bridge__{entity}.sql"] = staged_bridge(anchor, attributes, model)
        uss[f"{entity}.sql"] = dimension(anchor, attributes, model)
        models_staging.append(
            {
                "name": f"bridge__{entity}",
                "description": f"The staged bridge of {entity}: its own keys and those it reaches over its "
                "to-one ties, one row per interval over which none of them changes.",
                "data_tests": [{"unique": {"column_name": f"_key__{entity} || '@' || cast(_valid_from as varchar)"}}],
                "columns": [{"name": f"_key__{e}", "data_tests": ["not_null"]} for e in [entity, *reached]],
            }
            if reached
            else {
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
                    "data_tests": bridge_key_tests(e, warn=e in inherited),
                }
                for e in entities
            ],
        }
    )
    dump = lambda models: yaml.safe_dump({"version": 2, "models": models}, sort_keys=False, width=100)  # noqa: E731
    staging["uss_staging.yml"] = dump(models_staging)
    uss["uss.yml"] = dump(models_uss)
    return {STAGING: staging, USS: uss}


def generate(*, check: bool = False) -> int:
    """Write the models, or with ``check`` report drift: 0 written or clean, 1 drift, 2 invalid declarations."""
    try:
        schema, anchors = integrate.read(Path.cwd())
        tied = integrate.ties(Path.cwd(), schema, anchors)
        planned = packages(anchors, tied)
    except (integrate.ModelError, KeyError) as error:
        print(f"{integrate.MODEL}: {error}")
        return 2
    return ownership.run(GENERATOR, f"{integrate.MODEL}", planned, erd.region(GENERATOR, diagram(anchors)), check=check)


def main() -> int:
    parser = argparse.ArgumentParser(prog=GENERATOR, description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["generate"])
    parser.add_argument("--check", action="store_true", help="write nothing; report drift and exit 1 if any")
    args = parser.parse_args()
    return generate(check=args.check)
