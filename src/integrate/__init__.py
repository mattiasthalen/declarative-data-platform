"""Generate the integrate dbt models from the Anchor model and its mappings.

Reads ``anchor/model.yaml`` (a mirror of anchor.xsd, ADR-0004) and ``anchor/mappings/<anchor>.yaml``
and writes one package, ``models/integrate/anchor/``: per anchor its table, per attribute a posit
table, an annex table and the assembled view, the latest, point-in-time and time-traveling
perspectives, the key views, the integrity checks and Anchor's schema tracking, all in Roenbaeck's
default naming (ADR-0003).
The load itself is in ``macros/integrate/anchor.sql`` (ADR-0006).
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

import erd
import ownership

GENERATOR = "integrate"
MODEL = Path("anchor") / "model.yaml"
MAPPINGS = Path("anchor") / "mappings"
PACKAGE = Path("models") / "integrate" / "anchor"

# The model-wide settings ADR-0006 fixes, kept as Anchor's schema metadata so the database
# says what the model is (ADR-0008).
SCHEMA_METADATA = {
    "temporalization": "crt",
    "databaseTarget": "DuckDB",
    "changingRange": "timestamp",
    "encapsulation": "integrate",
    "identity": "int",
    "metadataPrefix": "Metadata",
    "metadataType": "int",
    "metadataUsage": "true",
    "changingSuffix": "ChangedAt",
    "identitySuffix": "ID",
    "positIdentity": "int",
    "positGenerator": "true",
    "positingRange": "timestamp",
    "positingSuffix": "PositedAt",
    "positorRange": "tinyint",
    "positorSuffix": "Positor",
    "reliabilityRange": "tinyint",
    "reliabilitySuffix": "Reliability",
    "reliableCutoff": "1",
    "deleteReliability": "0",
    "reliableSuffix": "Reliable",
    "partitioning": "false",
    "entityIntegrity": "true",
    "restatability": "false",
    "idempotency": "true",
    "assertiveness": "false",
    "decisiveness": "true",
    "naming": "improved",
    "positSuffix": "Posit",
    "annexSuffix": "Annex",
    "chronon": "timestamp",
    "now": "now()",
}
ATTRIBUTE_METADATA = {"capsule": "integrate", "restatable": "false", "idempotent": "true", "assertive": "false"}
TIE_METADATA = {"capsule": "integrate", "restatable": "false", "idempotent": "true", "assertive": "false"}
ANCHOR_METADATA = {"capsule": "integrate", "generator": "true"}


class ModelError(Exception):
    pass


# What each declared field may hold. Every one goes into SQL, Jinja or a file name.
MNEMONIC = re.compile(r"^[A-Z]{2,3}$")
DESCRIPTOR = re.compile(r"^[A-Z][A-Za-z0-9]*$")
SNAKE = re.compile(r"^[a-z][a-z0-9_]*$")
TYPE = re.compile(r"^[A-Za-z][A-Za-z0-9]*( [A-Za-z][A-Za-z0-9]*)*( ?\(\d+(, ?\d+)?\))?$")
NAME = re.compile(r"^[A-Za-z0-9_]+$")
JINJA = re.compile(r"\{[{%#]|[}%#]\}")


def texts(node) -> list[str]:
    """Every string in a parsed YAML document."""
    if isinstance(node, dict):
        return [t for k, v in node.items() for t in texts(k) + texts(v)]
    if isinstance(node, list):
        return [t for v in node for t in texts(v)]
    return [node] if isinstance(node, str) else []


def checked(value, pattern: re.Pattern, what: str) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise ModelError(f"{what} {value!r} does not match {pattern.pattern}")
    return value


def safe_yaml(path: Path) -> dict:
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (yaml.YAMLError, UnicodeDecodeError) as error:
        raise ModelError(f"{path} is not readable YAML: {error}") from error
    for text in texts(document):
        if JINJA.search(text):
            raise ModelError(f"{path}: {text!r} holds a Jinja delimiter")
    return document


@dataclass(frozen=True)
class Attribute:
    anchor: "Anchor"
    mnemonic: str
    descriptor: str
    data_range: str
    time_range: str
    description: str
    column: str

    @property
    def prefix(self) -> str:
        return f"{self.anchor.mnemonic}_{self.mnemonic}"

    @property
    def name(self) -> str:
        return f"{self.prefix}_{self.anchor.descriptor}_{self.descriptor}"

    @property
    def posit(self) -> str:
        return f"{self.name}_Posit"

    @property
    def annex(self) -> str:
        return f"{self.name}_Annex"


@dataclass(frozen=True)
class Anchor:
    mnemonic: str
    descriptor: str
    identity: str
    description: str
    route: str
    source: str
    changed_at: str

    @property
    def name(self) -> str:
        return f"{self.mnemonic}_{self.descriptor}"

    @property
    def id(self) -> str:
        return f"{self.mnemonic}_ID"

    @property
    def key_view(self) -> str:
        return f"key_{self.name}_{self.route}"


@dataclass(frozen=True)
class Tie:
    """A tie whose only identifier role is one anchor's, loaded by that anchor's mapping as an
    attribute of it whose value is the other role's identity (ADR-0036)."""

    owner: Anchor
    owner_role: str
    other: Anchor
    other_role: str
    other_key: Attribute
    time_range: str
    description: str
    column: str

    @property
    def name(self) -> str:
        return f"{self.owner.mnemonic}_{self.owner_role}_{self.other.mnemonic}_{self.other_role}"

    @property
    def posit(self) -> str:
        return f"{self.name}_Posit"

    @property
    def annex(self) -> str:
        return f"{self.name}_Annex"

    @property
    def identity_column(self) -> str:
        return f"{self.owner.id}_{self.owner_role}"

    @property
    def value_column(self) -> str:
        return f"{self.other.id}_{self.other_role}"


def as_list(value) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def read(root: Path) -> tuple[dict, list[tuple[Anchor, list[Attribute], Attribute]]]:
    schema = safe_yaml(root / MODEL).get("schema")
    if not isinstance(schema, dict):
        raise ModelError(f"{MODEL} has no schema")
    anchors = []
    for node in as_list(schema.get("anchor")):
        mnemonic = checked(node["mnemonic"], MNEMONIC, "anchor mnemonic")
        descriptor = checked(node["descriptor"], DESCRIPTOR, f"{mnemonic} descriptor")
        mapping_path = root / MAPPINGS / f"{mnemonic}_{descriptor}.yaml"
        if not mapping_path.is_file():
            raise ModelError(f"{mnemonic}_{descriptor} has no mapping at {mapping_path.relative_to(root)}")
        mapping = safe_yaml(mapping_path)
        columns = {
            m["attribute"]: checked(m["column"], SNAKE, f"{mnemonic}_{descriptor} column")
            for m in as_list(mapping.get("attributes"))
        }
        routes = [checked(i["route"], NAME, f"{mnemonic}_{descriptor} route") for i in as_list(node.get("identifier"))]
        if len(routes) != 1:
            raise ModelError(f"{mnemonic}_{descriptor} needs exactly one identifier route")
        anchor = Anchor(
            mnemonic=mnemonic,
            descriptor=descriptor,
            identity=checked(node.get("identity", "int"), TYPE, f"{mnemonic}_{descriptor} identity"),
            description=str(node.get("description") or "").strip(),
            route=routes[0],
            source=checked(mapping["source"], SNAKE, f"{mnemonic}_{descriptor} source"),
            changed_at=checked(mapping["changed_at"], SNAKE, f"{mnemonic}_{descriptor} changed_at"),
        )
        attributes = []
        identifier = None
        for item in as_list(node.get("attribute")):
            if item["mnemonic"] not in columns:
                raise ModelError(f"{anchor.name}: attribute {item['mnemonic']} has no column in its mapping")
            if "timeRange" not in item:
                raise ModelError(f"{anchor.name}: attribute {item['mnemonic']} must be historized")
            attribute = Attribute(
                anchor=anchor,
                mnemonic=checked(item["mnemonic"], MNEMONIC, f"{anchor.name} attribute mnemonic"),
                descriptor=checked(item["descriptor"], DESCRIPTOR, f"{anchor.name} attribute descriptor"),
                data_range=checked(item["dataRange"], TYPE, f"{anchor.name} dataRange"),
                time_range=checked(item["timeRange"], TYPE, f"{anchor.name} timeRange"),
                description=str(item.get("description") or "").strip(),
                column=columns[item["mnemonic"]],
            )
            attributes.append(attribute)
            keys = [k for k in as_list(item.get("key")) if k.get("route") == anchor.route and k.get("of") == mnemonic]
            if keys:
                identifier = attribute
        if identifier is None:
            raise ModelError(f"{anchor.name}: no attribute carries the key of route {anchor.route}")
        anchors.append((anchor, attributes, identifier))
    return schema, anchors


ROLE = re.compile(r"^[a-z][A-Za-z0-9]*$")


def source_columns(root: Path, source: str) -> set[str]:
    """The columns the contract staging ``source`` declares."""
    for path in sorted((root / "contracts").glob("*/*.yaml")):
        objects = safe_yaml(path).get("schema") or []
        if objects and objects[0].get("name") == source:
            return {str(p.get("name")) for p in objects[0].get("properties") or []}
    raise ModelError(f"no contract in contracts/ stages {source}")


def ties(root: Path, schema: dict, anchors: list[tuple[Anchor, list[Attribute], Attribute]]) -> list[Tie]:
    """Every tie of the model, each with the mapping entry that loads it. Only historized ties whose one
    identifier role is an anchor's, with one other anchor role, are supported (ADR-0036)."""
    by_mnemonic = {anchor.mnemonic: (anchor, identifier) for anchor, _, identifier in anchors}
    declared = {}
    for node in as_list(schema.get("tie")):
        if not isinstance(node, dict):
            raise ModelError(f"tie {node!r} is not a mapping")
        roles = []
        for r in as_list(node.get("role")):
            if not isinstance(r, dict):
                raise ModelError(f"tie role {r!r} is not a mapping")
            role = checked(r.get("role"), ROLE, "tie role")
            kind = checked(r.get("type"), MNEMONIC, f"tie role {role} type")
            if kind not in by_mnemonic:
                raise ModelError(f"tie role {role} plays {kind}, which is no anchor of the model")
            roles.append((role, kind, r.get("identifier") is True))
        name = "_".join(f"{kind}_{role}" for role, kind, _ in roles)
        identifiers = [r for r in roles if r[2]]
        if len(roles) != 2 or len(identifiers) != 1:
            raise ModelError(f"tie {name}: only a tie of two anchor roles, one of them its identifier, is supported")
        if not roles[0][2]:
            raise ModelError(f"tie {name}: list its identifier role first, so the tie is named as its models are")
        if "timeRange" not in node:
            raise ModelError(f"tie {name} must be historized")
        (owner_role, owner, _), (other_role, other, _) = roles
        declared[name] = (owner_role, owner, other_role, other, node)
    loaded = {}
    for anchor, _, _ in anchors:
        mapping_path = root / MAPPINGS / f"{anchor.name}.yaml"
        for entry in as_list(safe_yaml(mapping_path).get("ties")):
            name = entry.get("tie") if isinstance(entry, dict) else None
            if name not in declared:
                raise ModelError(f"{mapping_path.relative_to(root)}: tie {name!r} is not in {MODEL}")
            owner_role, owner, other_role, other, node = declared[name]
            if owner != anchor.mnemonic:
                raise ModelError(
                    f"{mapping_path.relative_to(root)}: tie {name} is loaded by the mapping of {owner}, "
                    "its identifier role, not of " + anchor.mnemonic
                )
            column = checked(entry.get("column"), SNAKE, f"tie {name} column")
            if column not in source_columns(root, anchor.source):
                raise ModelError(f"{mapping_path.relative_to(root)}: tie {name} column {column} is not in {anchor.source}")
            if name in loaded:
                raise ModelError(f"tie {name} is loaded twice")
            other_anchor, other_key = by_mnemonic[other]
            loaded[name] = Tie(
                owner=anchor,
                owner_role=owner_role,
                other=other_anchor,
                other_role=other_role,
                other_key=other_key,
                time_range=checked(node["timeRange"], TYPE, f"tie {name} timeRange"),
                description=str(node.get("description") or "").strip(),
                column=column,
            )
    missing = sorted(set(declared) - set(loaded))
    if missing:
        raise ModelError(f"tie {missing[0]} has no mapping entry that loads it")
    return [loaded[name] for name in declared]


def jinja_dict(values: dict) -> str:
    inner = ",\n".join(f"    {json.dumps(k)}: {json.dumps(v)}" for k, v in values.items())
    return "{% set a = {\n" + inner + "\n} %}\n"


def parameters(anchor: Anchor, identifier: Attribute, attribute: Attribute | None = None) -> dict:
    values = {
        "anchor": anchor.name,
        "anchor_mnemonic": anchor.mnemonic,
        "identity_type": anchor.identity,
        "source": anchor.source,
        "changed_at": anchor.changed_at,
        "key_column": identifier.column,
        "key_type": identifier.data_range,
        "key_view": anchor.key_view,
        "identifier_mnemonic": identifier.prefix,
        "identifier_value": identifier.name,
        "identifier_posit": identifier.posit,
        "identifier_annex": identifier.annex,
    }
    if attribute is not None:
        values |= {
            "mnemonic": attribute.prefix,
            "name": attribute.name,
            "identity_column": f"{attribute.prefix}_{anchor.id}",
            "value_column": attribute.name,
            "posit": attribute.posit,
            "annex": attribute.annex,
            "column": attribute.column,
            "value_type": attribute.data_range,
            "time_type": attribute.time_range,
            "is_identifier": attribute == identifier,
        }
    return values


def tie_parameters(tie: Tie, identifier: Attribute) -> dict:
    """The load's parameters for a tie: those of an attribute of its owner whose value is the other
    role's identity, found through the other anchor's key as known at each row's PositedAt (ADR-0037)."""
    return parameters(tie.owner, identifier) | {
        "mnemonic": tie.name,
        "name": tie.name,
        "identity_column": tie.identity_column,
        "value_column": tie.value_column,
        "posit": tie.posit,
        "annex": tie.annex,
        "column": tie.column,
        "value_type": tie.other.identity,
        "time_type": tie.time_range,
        "is_identifier": False,
        "reference_key": tie.other_key.name,
        "reference_key_mnemonic": tie.other_key.prefix,
        "reference_id": f"{tie.other_key.prefix}_{tie.other.id}",
        "reference_key_type": tie.other_key.data_range,
    }


def model(config: str, body: str, *, comment: str, values: dict | None = None, depends: list[str] = ()) -> str:
    lines = [f"-- {comment}", f"{{{{ config({config}) }}}}"]
    lines += [f"-- depends_on: {{{{ ref('{d}') }}}}" for d in depends]
    text = "\n".join(lines) + "\n"
    if values is not None:
        text += jinja_dict(values)
    return text + body.rstrip() + "\n"


def view(comment: str, body: str) -> str:
    return model("materialized='view'", body, comment=comment)


def violation(construct: str, kind: str, key: str, source: str, group: str, having: str = "count(*) > 1") -> str:
    return (
        f"select '{construct}' as Construct, '{kind}' as Violation, {key} as ViolationKey, "
        f"count(*) as Occurrences\nfrom {source}\ngroup by {group}\nhaving {having}"
    )


def json_key(*pairs: str) -> str:
    return "json_object(" + ", ".join(f"'{p}', \"{p}\"" for p in pairs) + ")"


def history_checks(
    name: str, *, m: str, posit: str, annex: str, identity: str, value: str, referenced: list, description: str
) -> dict[str, str]:
    """The ``ic_`` views of a historized attribute or tie: its posit's and annex's keys, the anchors
    each ``referenced`` column must name, and positor 0 asserting one value per identity and ChangedAt."""
    ref_posit, ref_annex = f"{{{{ ref('{posit}') }}}}", f"{{{{ ref('{annex}') }}}}"
    return {
        f"ic_{posit}.sql": view(
            f"What breaks the keys of {posit}.",
            "\nunion all\n".join(
                [
                    violation(posit, "duplicate primary key", json_key(f"{m}_ID"), ref_posit, f'"{m}_ID"'),
                    violation(
                        posit,
                        "duplicate unique key",
                        json_key(identity, f"{m}_ChangedAt", value),
                        ref_posit,
                        f'"{identity}", "{m}_ChangedAt", "{value}"',
                    ),
                ]
                + [
                    (
                        f"select '{posit}', 'no row in {anchor.name} for {column}', "
                        f"json_object('{column}', c.\"{column}\"), count(*)\n"
                        f"from {ref_posit} c\nleft join {{{{ ref('{anchor.name}') }}}} p on p.\"{anchor.id}\" = c.\"{column}\"\n"
                        f'where p."{anchor.id}" is null\ngroup by c."{column}"'
                    )
                    for anchor, column in referenced
                ]
            ),
        ),
        f"ic_{annex}.sql": view(
            f"What breaks the keys of {annex}.",
            "\nunion all\n".join(
                [
                    violation(
                        annex,
                        "duplicate primary key",
                        json_key(f"{m}_ID", f"{m}_Positor", f"{m}_PositedAt"),
                        ref_annex,
                        f'"{m}_ID", "{m}_Positor", "{m}_PositedAt"',
                    ),
                    (
                        f"select '{annex}', 'no row in {posit} for {m}_ID', "
                        f"json_object('{m}_ID', c.\"{m}_ID\"), count(*)\n"
                        f"from {ref_annex} c\nleft join {ref_posit} p on p.\"{m}_ID\" = c.\"{m}_ID\"\n"
                        f'where p."{m}_ID" is null\ngroup by c."{m}_ID"'
                    ),
                ]
            ),
        ),
        f"ic_{name}.sql": view(
            description,
            (
                f"select '{name}' as Construct, 'more than one assertion at a time' as Violation,\n"
                f"    json_object('{m}_Positor', 0, '{identity}', \"{identity}\", '{m}_ChangedAt', \"{m}_ChangedAt\") "
                "as ViolationKey,\n    count(*) as Occurrences\n"
                f"from (\n    {{{{ anchor_latest({{'mnemonic': '{m}', 'name': '{name}'}}) }}}}\n)\n"
                f'group by "{identity}", "{m}_ChangedAt"\nhaving count(*) > 1'
            ),
        ),
    }


def integrity_files(anchor: Anchor, attributes: list[Attribute], identifier: Attribute) -> dict[str, str]:
    files = {}
    a = anchor.id
    files[f"ic_{anchor.name}.sql"] = view(
        f"What breaks the keys of {anchor.name}.",
        violation(anchor.name, "duplicate primary key", json_key(a), f"{{{{ ref('{anchor.name}') }}}}", f'"{a}"'),
    )
    for t in attributes:
        m = t.prefix
        files |= history_checks(
            t.name, m=m, posit=t.posit, annex=t.annex, identity=f"{m}_{a}", value=t.name,
            referenced=[(anchor, f"{m}_{a}")],
            description=f"What {t.posit} and {t.annex} say together: positor 0 asserting more than one value "
            "for one identity and ChangedAt at its latest PositedAt (the model is decisive).",
        )
    k = identifier
    files[f"ic_{anchor.key_view}.sql"] = view(
        f"Keys of {anchor.name} that more than one identity has, and identities with more than one key.",
        (
            f"select '{anchor.key_view}' as Construct, 'duplicate natural key' as Violation,\n"
            f"    json_object('{k.name}', \"{k.name}\") as ViolationKey, count(*) as Occurrences\n"
            f"from {{{{ ref('{anchor.key_view}') }}}}\n"
            f'group by "{k.name}"\nhaving count(*) > 1\n'
            "union all\n"
            f"select '{anchor.key_view}', 'more than one natural key', json_object('{a}', \"{a}\"), count(*)\n"
            f"from {{{{ ref('{anchor.key_view}') }}}}\n"
            f'group by "{a}"\nhaving count(*) > 1'
        ),
    )
    return files


def anchor_files(anchor: Anchor, attributes: list[Attribute], identifier: Attribute) -> dict[str, str]:
    files: dict[str, str] = {}
    files[f"{anchor.name}.sql"] = model(
        "materialized='incremental'",
        "{{ anchor_anchor(a) }}",
        comment=f"The {anchor.name} anchor: one identity per {identifier.descriptor} (ADR-0005).",
        values=parameters(anchor, identifier),
    )
    for t in attributes:
        values = parameters(anchor, identifier, t)
        depends = [anchor.name] if t == identifier else []
        files[f"{t.posit}.sql"] = model(
            "materialized='incremental'",
            "{{ anchor_posit(a) }}",
            comment=f"The posits of {t.name}: every value asserted at a ChangedAt.",
            values=values,
            depends=depends,
        )
        files[f"{t.annex}.sql"] = model(
            "materialized='incremental'",
            "{{ anchor_annex(a) }}",
            comment=f"The annex of {t.name}: who asserted or retracted each posit, when, and in which batch.",
            values=values,
            depends=depends,
        )
        files[f"{t.name}.sql"] = model(
            "materialized='view'",
            "{{ anchor_assembled(a) }}",
            comment=f"{t.name} assembled: every annex row with its posit.",
            values=values,
        )

    k = identifier
    files[f"{anchor.key_view}.sql"] = model(
        "materialized='view'",
        "{{ anchor_key_select(a, ref(a.identifier_posit), ref(a.identifier_annex)) }}",
        comment=f"The {anchor.route} key of every {anchor.name} identity, from the latest {k.descriptor}.",
        values=parameters(anchor, identifier),
    )
    files[f"p{anchor.key_view}.sql"] = view(
        f"The {anchor.route} key of every {anchor.name} identity over changing time: each value from its "
        "ChangedAt until the next. A key at a time T is the row with ChangedAt <= T < ChangedBefore.",
        (
            f'select "{anchor.id}", "{k.name}", changed_at as "ChangedAt",\n'
            f"    lead(changed_at, 1, cast('9999-12-31' as timestamp)) over (\n"
            f'        partition by "{anchor.id}" order by changed_at\n    ) as "ChangedBefore"\n'
            "from (\n"
            f'    select "{k.prefix}_{anchor.id}" as "{anchor.id}", "{k.name}", "{k.prefix}_ChangedAt" as changed_at\n'
            f"    from (\n        {{{{ anchor_latest({{'mnemonic': '{k.prefix}', 'name': '{k.name}'}}) }}}}\n    )\n"
            ")"
        ),
    )

    files[f"l{anchor.name}.sql"] = view(
        f"The latest perspective of {anchor.name}: per identity, each attribute's latest reliable "
        "value as positor 0 states it now.",
        perspective(anchor, attributes),
    )
    files[f"p{anchor.name}.sql"] = model(
        "materialized='table_macro', parameters=['changingTimepoint']",
        perspective(anchor, attributes, changed_by="changingTimepoint"),
        comment=f"The point-in-time perspective of {anchor.name}, a table macro taking changingTimepoint: per "
        "identity, each attribute's latest reliable value as positor 0 states it, of those that changed at or "
        "before changingTimepoint; nothing before an attribute's first ChangedAt (ADR-0030).",
    )
    files[f"t{anchor.name}.sql"] = model(
        "materialized='table_macro', parameters=['changingTimepoint', 'positingTimepoint']",
        perspective(anchor, attributes, changed_by="changingTimepoint", posited_by="positingTimepoint"),
        comment=f"The time-traveling perspective of {anchor.name}, a table macro taking changingTimepoint and "
        "positingTimepoint: per identity, each attribute's latest reliable value as positor 0 had stated it by "
        "positingTimepoint, of those that changed at or before changingTimepoint (ADR-0033).",
    )
    files |= integrity_files(anchor, attributes, identifier)
    return files


def tie_files(tie: Tie, identifier: Attribute) -> dict[str, str]:
    """A tie's posit and annex tables, assembled view, perspectives and key checks (ADR-0036)."""
    files: dict[str, str] = {}
    values = tie_parameters(tie, identifier)
    depends = [tie.other_key.name]
    files[f"{tie.posit}.sql"] = model(
        "materialized='incremental'",
        "{{ anchor_posit(a) }}",
        comment=f"The posits of {tie.name}: every {tie.other.descriptor} a {tie.owner.descriptor} was tied to at a ChangedAt.",
        values=values,
        depends=depends,
    )
    files[f"{tie.annex}.sql"] = model(
        "materialized='incremental'",
        "{{ anchor_annex(a) }}",
        comment=f"The annex of {tie.name}: who asserted or retracted each posit, when, and in which batch.",
        values=values,
        depends=depends,
    )
    files[f"{tie.name}.sql"] = model(
        "materialized='view'",
        "{{ anchor_assembled(a) }}",
        comment=f"{tie.name} assembled: every annex row with its posit.",
        values=values,
    )
    files[f"l{tie.name}.sql"] = view(
        f"The latest perspective of {tie.name}: per {tie.owner.descriptor}, its latest reliable "
        f"{tie.other.descriptor} as positor 0 states it now.",
        tie_perspective(tie),
    )
    files[f"p{tie.name}.sql"] = model(
        "materialized='table_macro', parameters=['changingTimepoint']",
        tie_perspective(tie, changed_by="changingTimepoint"),
        comment=f"The point-in-time perspective of {tie.name}, a table macro taking changingTimepoint (ADR-0030).",
    )
    files[f"t{tie.name}.sql"] = model(
        "materialized='table_macro', parameters=['changingTimepoint', 'positingTimepoint']",
        tie_perspective(tie, changed_by="changingTimepoint", posited_by="positingTimepoint"),
        comment=f"The time-traveling perspective of {tie.name}, a table macro taking changingTimepoint and "
        "positingTimepoint (ADR-0033).",
    )
    files |= history_checks(
        tie.name, m=tie.name, posit=tie.posit, annex=tie.annex, identity=tie.identity_column,
        value=tie.value_column, referenced=[(tie.owner, tie.identity_column), (tie.other, tie.value_column)],
        description=f"The key of {tie.name}: positor 0 asserting more than one {tie.other.descriptor} for one "
        f"{tie.owner.descriptor} and ChangedAt at its latest PositedAt.",
    )
    return files


def tie_perspective(tie: Tie, changed_by: str | None = None, posited_by: str | None = None) -> str:
    """Per identifier identity, the tie's latest reliable version; as of ``changed_by`` and as known at
    ``posited_by`` when given, as ``perspective`` does for an anchor's attributes."""
    m = tie.name
    cutoff = f", '{changed_by}'" if changed_by else ""
    if posited_by:
        cutoff += f", posited_by='{posited_by}'"
    columns = [f'"Metadata_{m}"', f'"{m}_ID"', f'"{m}_ChangedAt"', f'"{m}_PositedAt"', f'"{m}_Positor"',
               f'"{m}_Reliability"', f'"{tie.identity_column}"', f'"{tie.value_column}"']
    return (
        "select\n" + ",\n".join(f"    {c}" for c in columns) + "\nfrom (\n"
        f"    {{{{ anchor_latest({{'mnemonic': '{m}', 'name': '{m}'}}{cutoff}) }}}}\n)\n"
        f'qualify row_number() over (partition by "{tie.identity_column}" order by "{m}_ChangedAt" desc) = 1'
    )


def perspective(
    anchor: Anchor, attributes: list[Attribute], changed_by: str | None = None, posited_by: str | None = None
) -> str:
    """The latest perspective's select, the anchor joined to each attribute's latest version; with
    ``changed_by``, the point-in-time perspective's, as of that SQL expression; with ``posited_by`` too,
    the time-traveling perspective's, as known at that one."""
    joins, columns = [], [f'    p."{anchor.id}"', f'    p."Metadata_{anchor.mnemonic}"']
    cutoff = f", '{changed_by}'" if changed_by else ""
    if posited_by:
        cutoff += f", posited_by='{posited_by}'"
    for t in attributes:
        m = t.prefix
        alias = t.mnemonic.lower()
        columns += [
            f'    {alias}."Metadata_{m}"',
            f'    {alias}."{m}_{anchor.id}"',
            f'    {alias}."{m}_ID"',
            f'    {alias}."{m}_ChangedAt"',
            f'    {alias}."{m}_PositedAt"',
            f'    {alias}."{m}_Positor"',
            f'    {alias}."{m}_Reliability"',
            f'    {alias}."{t.name}"',
        ]
        joins.append(
            f"left join (\n    select * from (\n        {{{{ anchor_latest({{'mnemonic': '{m}', 'name': '{t.name}'}}{cutoff}) }}}}\n    )\n"
            f'    qualify row_number() over (partition by "{m}_{anchor.id}" order by "{m}_ChangedAt" desc) = 1\n'
            f') {alias} on {alias}."{m}_{anchor.id}" = p."{anchor.id}"'
        )
    return "select\n" + ",\n".join(columns) + f"\nfrom {{{{ ref('{anchor.name}') }}}} p\n" + "\n".join(joins)


def schema_json(schema: dict, anchors: list[tuple[Anchor, list[Attribute], Attribute]], tied: list[Tie]) -> str:
    """The model as Anchor's jsonified XML: constructs keyed by mnemonic (CreateSchemaTracking)."""
    out_anchors = {}
    for anchor, attributes, identifier in anchors:
        out_attributes = {}
        for t in attributes:
            node = {
                "descriptor": t.descriptor,
                "dataRange": t.data_range,
                "timeRange": t.time_range,
                "metadata": ATTRIBUTE_METADATA,
                "description": t.description,
            }
            if t == identifier:
                node["key"] = [{"stop": "1", "route": anchor.route, "of": anchor.mnemonic, "branch": "1"}]
            out_attributes[t.mnemonic] = node
        out_anchors[anchor.mnemonic] = {
            "descriptor": anchor.descriptor,
            "identity": anchor.identity,
            "metadata": ANCHOR_METADATA,
            "description": anchor.description,
            "identifier": [{"route": anchor.route}],
            "attributes": [t.mnemonic for t in attributes],
            "attribute": out_attributes,
        }
    document = {
        "schema": {
            "format": "0.99",
            "metadata": SCHEMA_METADATA,
            "description": str(schema.get("description") or "").strip(),
            "knot": {},
            "anchor": out_anchors,
            "nexus": {},
            "tie": {
                tie.name: {
                    "timeRange": tie.time_range,
                    "metadata": TIE_METADATA,
                    "description": tie.description,
                    "roles": [tie.owner_role, tie.other_role],
                    "role": [
                        {"role": tie.owner_role, "type": tie.owner.mnemonic, "identifier": "true"},
                        {"role": tie.other_role, "type": tie.other.mnemonic, "identifier": "false"},
                    ],
                }
                for tie in tied
            },
        }
    }
    return json.dumps(document, ensure_ascii=False, sort_keys=False, separators=(",", ":"))


def tracking_files(schema: dict, anchors, tied: list[Tie]) -> dict[str, str]:
    text = schema_json(schema, anchors, tied).replace("'", "''")
    files = {
        "_Schema.sql": model(
            "materialized='incremental'",
            "{% raw %}\nwith model as (\n    select cast('" + text + "' as json) as schema\n)\n{% endraw %}\n"
            "select\n"
            "    cast({% if is_incremental() %}(select coalesce(max(version), 0) from {{ this }}){% else %}0{% endif %} + 1 as integer) as version,\n"
            "    cast(now() as timestamp) as activation,\n"
            "    schema\n"
            "from model\n"
            "{% if is_incremental() %}\n"
            "where cast(schema as varchar) is distinct from (\n"
            "    select cast(schema as varchar) from {{ this }} order by version desc limit 1\n"
            ")\n"
            "{% endif %}",
            comment="Every version of the Anchor model this database has held, as JSON (ADR-0008).",
        ),
    }
    expanded = ",\n".join(
        f"    s.schema->'schema'->'metadata'->>'{key}' as {key}" for key in SCHEMA_METADATA
    )
    files["_Schema_Expanded.sql"] = view(
        "The schema table with the model's metadata as columns.",
        "select\n    s.version,\n    s.activation,\n    s.schema->'schema'->>'format' as format,\n"
        + expanded
        + "\nfrom {{ ref('_Schema') }} s",
    )
    files["_Anchor.sql"] = view(
        "Every anchor of every model version.",
        """select
    s.version,
    s.activation,
    s.schema->'schema'->'metadata'->>'temporalization' as temporalization,
    a.mnemonic || '_' || (s.schema->'schema'->'anchor'->a.mnemonic->>'descriptor') as name,
    s.schema->'schema'->'anchor'->a.mnemonic->>'descriptor' as descriptor,
    a.mnemonic,
    s.schema->'schema'->'anchor'->a.mnemonic->'metadata'->>'capsule' as capsule,
    s.schema->'schema'->'anchor'->a.mnemonic->>'identity' as identity,
    s.schema->'schema'->'anchor'->a.mnemonic->'metadata'->>'generator' as generator,
    coalesce(json_array_length(s.schema->'schema'->'anchor'->a.mnemonic->'attributes'), 0) as numberOfAttributes,
    s.schema->'schema'->'anchor'->a.mnemonic->>'description' as description
from {{ ref('_Schema') }} s, unnest(json_keys(s.schema->'schema'->'anchor')) as a(mnemonic)""",
    )
    files["_Attribute.sql"] = view(
        "Every attribute of every model version.",
        """select
    s.version,
    s.activation,
    s.schema->'schema'->'metadata'->>'temporalization' as temporalization,
    x.anchor || '_' || x.mnemonic || '_' || (x.a->>'descriptor') || '_' || (x.t->>'descriptor') as name,
    x.t->>'descriptor' as descriptor,
    x.mnemonic,
    x.t->'metadata'->>'capsule' as capsule,
    x.t->>'dataRange' as dataRange,
    (x.t->>'knotRange') is not null as knotted,
    x.t->>'knotRange' as knotRange,
    (x.t->>'timeRange') is not null as historized,
    x.t->>'timeRange' as timeRange,
    x.t->'metadata'->>'generator' as generator,
    x.t->'metadata'->>'assertive' as assertive,
    x.t->'metadata'->>'restatable' as restatable,
    x.t->'metadata'->>'idempotent' as idempotent,
    x.anchor as anchorMnemonic,
    x.a->>'descriptor' as anchorDescriptor,
    x.a->>'identity' as anchorIdentity,
    x.t->>'description' as description,
    coalesce(json_array_length(x.t->'key'), 0) as numberOfKeyStops
from {{ ref('_Schema') }} s,
lateral (
    select
        a.anchor,
        s.schema->'schema'->'anchor'->a.anchor as a,
        t.mnemonic,
        s.schema->'schema'->'anchor'->a.anchor->'attribute'->t.mnemonic as t
    from unnest(json_keys(s.schema->'schema'->'anchor')) as a(anchor),
        unnest(json_keys(s.schema->'schema'->'anchor'->a.anchor->'attribute')) as t(mnemonic)
) x""",
    )
    files["_Knot.sql"] = view(
        "Every knot of every model version.",
        """select
    s.version,
    s.activation,
    s.schema->'schema'->'metadata'->>'temporalization' as temporalization,
    k.mnemonic || '_' || (s.schema->'schema'->'knot'->k.mnemonic->>'descriptor') as name,
    s.schema->'schema'->'knot'->k.mnemonic->>'descriptor' as descriptor,
    k.mnemonic,
    s.schema->'schema'->'knot'->k.mnemonic->'metadata'->>'capsule' as capsule,
    s.schema->'schema'->'knot'->k.mnemonic->>'dataRange' as dataRange,
    s.schema->'schema'->'knot'->k.mnemonic->>'identity' as identity,
    s.schema->'schema'->'knot'->k.mnemonic->>'description' as description
from {{ ref('_Schema') }} s, unnest(json_keys(s.schema->'schema'->'knot')) as k(mnemonic)""",
    )
    files["_Tie.sql"] = view(
        "Every tie of every model version.",
        """select
    s.version,
    s.activation,
    s.schema->'schema'->'metadata'->>'temporalization' as temporalization,
    t.name,
    s.schema->'schema'->'tie'->t.name->'metadata'->>'capsule' as capsule,
    (s.schema->'schema'->'tie'->t.name->>'timeRange') is not null as historized,
    s.schema->'schema'->'tie'->t.name->>'timeRange' as timeRange,
    s.schema->'schema'->'tie'->t.name->>'description' as description
from {{ ref('_Schema') }} s, unnest(json_keys(s.schema->'schema'->'tie')) as t(name)""",
    )
    return files


def schema_file(anchors, tied: list[Tie]) -> str:
    models = []
    for anchor, attributes, identifier in anchors:
        models.append({"name": anchor.name, "description": anchor.description})
        for t in attributes:
            models.append({"name": t.name, "description": t.description})
    for tie in tied:
        models.append({"name": tie.name, "description": tie.description})
        # A tie's key checks warn rather than fail the build, outside IntegrityViolations ([7]).
        for check in (f"ic_{tie.posit}", f"ic_{tie.annex}", f"ic_{tie.name}"):
            models.append(
                {
                    "name": check,
                    "description": f"What breaks the keys of {tie.name}; a row warns.",
                    "data_tests": [{"empty": {"config": {"severity": "warn"}}}],
                }
            )
    models.append(
        {
            "name": "IntegrityViolations",
            "description": "Every integrity check of the model; empty when nothing is wrong.",
            "data_tests": ["empty"],
        }
    )
    return yaml.safe_dump({"version": 2, "models": models}, sort_keys=False, allow_unicode=True, width=100)


def diagram(anchors: list[tuple[Anchor, list[Attribute], Attribute]], tied: list[Tie]) -> str:
    """Each anchor with its identity and its attributes, and each tie as a relationship named for it,
    many of its identifier role to one of the other; knots and load tables are left out."""
    return erd.diagram(
        [
            (
                anchor.name,
                [erd.row(anchor.identity, anchor.id, "PK")]
                + [erd.row(t.data_range, t.name, comment="historized") for t in attributes],
            )
            for anchor, attributes, _ in anchors
        ],
        [f'{t.owner.name} }}o--|| {t.other.name} : "{t.name}"' for t in tied],
    )


def packages(
    schema: dict, anchors: list[tuple[Anchor, list[Attribute], Attribute]], tied: list[Tie]
) -> dict[Path, dict[str, str]]:
    files: dict[str, str] = {}
    for anchor, attributes, identifier in anchors:
        files |= anchor_files(anchor, attributes, identifier)
    checks = [name.removesuffix(".sql") for name in files if name.startswith("ic_")]
    identifiers = {anchor.mnemonic: identifier for anchor, _, identifier in anchors}
    for tie in tied:
        files |= tie_files(tie, identifiers[tie.owner.mnemonic])
    files["IntegrityViolations.sql"] = view(
        "Every integrity check of the model in one view: a row is something wrong.",
        "select\n    cast(null as varchar) as Construct,\n    cast(null as varchar) as Violation,\n"
        "    cast(null as json) as ViolationKey,\n    cast(null as bigint) as Occurrences\nwhere false\n"
        + "\n".join(f"union all select * from {{{{ ref('{c}') }}}}" for c in checks),
    )
    files |= tracking_files(schema, anchors, tied)
    files["anchor.yml"] = schema_file(anchors, tied)
    return {PACKAGE: files}


def generate(*, check: bool = False) -> int:
    """Write the models, or with ``check`` report drift: 0 written or clean, 1 drift, 2 invalid declarations."""
    try:
        schema, anchors = read(Path.cwd())
        tied = ties(Path.cwd(), schema, anchors)
        planned = packages(schema, anchors, tied)
    except (ModelError, KeyError) as error:
        print(f"{MODEL}: {error}")
        return 2
    return ownership.run(
        GENERATOR, f"{MODEL} and {MAPPINGS}/", planned, erd.region(GENERATOR, diagram(anchors, tied)), check=check
    )


def main() -> int:
    parser = argparse.ArgumentParser(prog=GENERATOR, description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["generate"])
    parser.add_argument("--check", action="store_true", help="write nothing; report drift and exit 1 if any")
    args = parser.parse_args()
    return generate(check=args.check)
