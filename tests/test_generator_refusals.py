"""Generators refuse declarations that would put anything but a declared name or type into SQL (F19).

A contract's object name is snake_case; a physicalName holds no Jinja delimiter; a
``transformLogic`` only rewrites its own ``value``. A model's description holds no Jinja, and
an attribute's mnemonic and dataRange are a plain identifier and a plain type. Each refusal
exits non-zero and writes nothing; the benign edit beside it is accepted, so the refusal is
for the named reason and not for breaking the declaration's shape.

Each test runs ``uv run <layer> generate`` in one shared copy of the repo and restores the
declarations it touched.
"""

from __future__ import annotations

import re
from collections.abc import Callable

import pytest
import yaml

from harness import CONTRACT, CONTRACT_PATH, Step, Workspace, require

MODEL_PATH = "anchor/model.yaml"
MAPPING_PATH = "anchor/mappings/PR_Product.yaml"
SUBCATEGORY_MAPPING_PATH = "anchor/mappings/PS_ProductSubcategory.yaml"
TIE = "PR_in_PS_contains"
TIE_COLUMN = "product_subcategory_id"


@pytest.fixture(scope="module")
def shared(make_workspace) -> Workspace:
    return make_workspace("refusals")


@pytest.fixture
def ws(shared):
    paths = (CONTRACT_PATH, MODEL_PATH, MAPPING_PATH, SUBCATEGORY_MAPPING_PATH)
    originals = {p: (shared.root / p).read_text() for p in paths if (shared.root / p).exists()}
    yield shared
    for p in paths:
        if p in originals:
            (shared.root / p).write_text(originals[p])
        else:
            (shared.root / p).unlink(missing_ok=True)
    require(shared.generate())


def edit(ws: Workspace, path: str, change: Callable[[dict], None]) -> None:
    file = ws.root / path
    document = yaml.safe_load(file.read_text())
    change(document)
    file.write_text(yaml.safe_dump(document, sort_keys=False, allow_unicode=True))


def refused(ws: Workspace, layer: str) -> Step:
    before = ws.tree()
    step = ws.run("uv", "run", layer, "generate")
    assert step.returncode != 0, f"{layer} generate accepted it:\n{step.output[-3000:]}"
    after = ws.tree()
    written = sorted(
        p for p in set(before) | set(after) if p.startswith("models/") and before.get(p) != after.get(p)
    )
    assert written == [], f"{layer} generate wrote while refusing: {written}"
    return step


def accepted(ws: Workspace, layer: str) -> None:
    require(ws.run("uv", "run", layer, "generate"))


# --------------------------------------------------------------------------- conform


def _object(contract: dict) -> dict:
    return contract["schema"][0]


def _property(contract: dict, name: str) -> dict:
    return next(p for p in _object(contract)["properties"] if p["name"] == name)


def test_conform_accepts_trim_value(ws):
    """F19: trim(value) on another property is a rewrite of its own value, and is accepted."""
    edit(ws, CONTRACT_PATH, lambda c: _property(c, "color").update(transformLogic="trim(value)"))
    accepted(ws, "conform")


def test_conform_refuses_object_name_not_snake_case(ws):
    """F19: an object name that is not snake_case is refused."""
    edit(ws, CONTRACT_PATH, lambda c: _object(c).update(name="AdventureWorks__Products"))
    refused(ws, "conform")


@pytest.mark.parametrize("where", ["object", "property"])
def test_conform_refuses_jinja_in_physical_name(ws, where):
    """F19: a physicalName holding a Jinja delimiter is refused, on the object or on a property."""

    def change(c):
        target = _object(c) if where == "object" else _property(c, "name")
        target["physicalName"] = target["physicalName"] + "{{ 1 }}"

    edit(ws, CONTRACT_PATH, change)
    refused(ws, "conform")


@pytest.mark.parametrize(
    "logic",
    ["read_text('/etc/passwd')", "trim(read_text('/etc/passwd'))", "trim(name)"],
)
def test_conform_refuses_logic_beyond_its_own_value(ws, logic):
    """F19: a transformLogic that reads a file or another column is refused."""
    edit(ws, CONTRACT_PATH, lambda c: _property(c, "product_line").update(transformLogic=logic))
    refused(ws, "conform")



@pytest.mark.parametrize("logic", ["coalesce(value, #1)", "concat(value, $1)", 'trim("value")'])
def test_conform_refuses_logic_reaching_a_column_by_position_or_quoted_name(ws, logic):
    """F19: a transformLogic that reaches another column by position (``#1``, ``$1``) or by a
    quoted identifier (``"value"`` names a column, not the property's own value) is refused."""
    edit(ws, CONTRACT_PATH, lambda c: _property(c, "product_line").update(transformLogic=logic))
    refused(ws, "conform")


def test_conform_refuses_contract_whose_file_is_not_its_resource(ws):
    """D9: a contract's file names the resource it reads (contracts/<source>/<resource>.yaml reads
    <source>__<resource>). The products contract copied unchanged to items.yaml still reads
    adventure_works__products, and is refused, naming the file."""
    copied = ws.root / "contracts" / "adventure_works" / "items.yaml"
    copied.write_text((ws.root / CONTRACT_PATH).read_text())
    try:
        step = refused(ws, "conform")
        assert "items.yaml" in step.output, step.output[-3000:]
    finally:
        copied.unlink()


GENERATED_CONFORM = f"models/conform/adventure_works/{CONTRACT}.sql"
SQL_LITERAL = re.compile(r"'(?:[^']|'')*'")


@pytest.mark.parametrize(
    "logic",
    [
        "case when value in ('R','M') then trim(value) end",
        "case when (value = '') then null else value end",
        "replace(value, 'value', 'v')",
        "trim(VALUE)",
    ],
)
def test_conform_accepts_logic_over_its_own_value(ws, logic):
    """F19: a transformLogic that rewrites only its own value is accepted, whatever the case of
    ``value``; every ``value`` outside a literal is substituted and every literal is kept."""
    edit(ws, CONTRACT_PATH, lambda c: _property(c, "product_line").update(transformLogic=logic))
    accepted(ws, "conform")
    sql = (ws.root / GENERATED_CONFORM).read_text()
    for literal in SQL_LITERAL.findall(logic):
        assert literal in sql, f"the literal {literal} of {logic!r} did not survive:\n{sql}"
    bare = re.findall(r"\bvalue\b", SQL_LITERAL.sub("''", sql), flags=re.IGNORECASE)
    assert bare == [], f"{logic!r} left {bare} unsubstituted:\n{sql}"


@pytest.mark.parametrize(
    "logic",
    ["trim(value) --", "trim(value) /* x */", "trim(value) || 'abc"],
)
def test_conform_refuses_comments_and_unterminated_literals(ws, logic):
    """F19: a transformLogic holding a comment or an unterminated literal is refused."""
    edit(ws, CONTRACT_PATH, lambda c: _property(c, "product_line").update(transformLogic=logic))
    refused(ws, "conform")


# --------------------------------------------------------------------------- integrate


def _anchor(model: dict) -> dict:
    return next(a for a in model["schema"]["anchor"] if a["mnemonic"] == "PR")


def _attribute(model: dict, mnemonic: str) -> dict:
    return next(a for a in _anchor(model)["attribute"] if a["mnemonic"] == mnemonic)


def _rename_col(ws: Workspace, mnemonic: str) -> None:
    edit(ws, MODEL_PATH, lambda m: _attribute(m, "COL").update(mnemonic=mnemonic))

    def mapping(d):
        next(a for a in d["attributes"] if a["attribute"] == "COL")["attribute"] = mnemonic

    edit(ws, MAPPING_PATH, mapping)


def test_integrate_accepts_plain_changes(ws):
    """F19: a plain description, mnemonic and dataRange are accepted."""
    edit(ws, MODEL_PATH, lambda m: m["schema"].update(description=m["schema"]["description"] + " Revised."))
    edit(ws, MODEL_PATH, lambda m: _attribute(m, "COL").update(dataRange="varchar(20)"))
    _rename_col(ws, "CLR")
    accepted(ws, "integrate")


@pytest.mark.parametrize("where", ["model", "anchor", "attribute"])
def test_integrate_refuses_jinja_in_description(ws, where):
    """F19: a description holding {% endraw %} is refused."""

    def change(m):
        target = {"model": m["schema"], "anchor": _anchor(m), "attribute": _attribute(m, "NAM")}[where]
        target["description"] = target["description"] + " {% endraw %}{{ 7 * 7 }}{% raw %}"

    edit(ws, MODEL_PATH, change)
    refused(ws, "integrate")


def test_integrate_refuses_mnemonic_not_an_identifier(ws):
    """F19: an attribute mnemonic that is not a plain identifier is refused (model and mapping agree)."""
    _rename_col(ws, "C);--")
    refused(ws, "integrate")


@pytest.mark.parametrize("data_range", ["varchar(15)); drop table x; --", "{{ 1 }}", "varchar(15) || 'x'"])
def test_integrate_refuses_data_range_not_a_type(ws, data_range):
    """F19: a dataRange that is not a plain type is refused."""
    edit(ws, MODEL_PATH, lambda m: _attribute(m, "COL").update(dataRange=data_range))
    refused(ws, "integrate")


# --------------------------------------------------------------------------- story #6: a tie in a mapping


def _tie_entry(mapping: dict) -> dict:
    """The entry of PR_Product's mapping that loads the tie: the one under ``ties`` naming it."""
    entries = mapping.get("ties") or []
    found = [e for e in entries if isinstance(e, dict) and TIE in e.values()]
    assert len(found) == 1, f"{MAPPING_PATH} has {len(found)} tie entries naming {TIE}: {entries}"
    return found[0]


def _replace_value(entry: dict, old: str, new: str) -> None:
    keys = [k for k, v in entry.items() if v == old]
    assert len(keys) == 1, f"the tie entry {entry} holds {old!r} under {len(keys)} keys"
    entry[keys[0]] = new


def _refused_naming(ws: Workspace, name: str) -> None:
    step = refused(ws, "integrate")
    assert step.returncode == 2, f"integrate generate exited {step.returncode}, not 2:\n{step.output[-3000:]}"
    assert name in step.output, f"the refusal does not name {name!r}:\n{step.output[-3000:]}"


def test_integrate_accepts_the_tie_mapping(ws):
    """EC7 ([3]): the committed tie entry in PR_Product's mapping is accepted, so the refusals beside it
    are for their named reason."""
    _tie_entry(yaml.safe_load((ws.root / MAPPING_PATH).read_text()))
    accepted(ws, "integrate")


def test_integrate_refuses_tie_the_model_lacks(ws):
    """EC7 ([3]): a mapping's tie entry naming a tie the model does not declare is refused with exit 2,
    naming it."""
    edit(ws, MAPPING_PATH, lambda m: _replace_value(_tie_entry(m), TIE, "PR_in_PS_holds"))
    _refused_naming(ws, "PR_in_PS_holds")


def test_integrate_refuses_tie_column_the_contract_lacks(ws):
    """EC7 ([3]): a tie entry naming a column the mapping's contract lacks is refused with exit 2, naming it."""
    edit(ws, MAPPING_PATH, lambda m: _replace_value(_tie_entry(m), TIE_COLUMN, "product_subcategory_key"))
    _refused_naming(ws, "product_subcategory_key")


def test_integrate_refuses_tie_whose_identifier_is_another_anchor(ws):
    """EC7 ([3]): the tie entry copied into PS_ProductSubcategory's mapping, whose anchor is not the tie's
    identifier role, is refused with exit 2, naming the tie, though the column is in that contract."""
    entry = dict(_tie_entry(yaml.safe_load((ws.root / MAPPING_PATH).read_text())))

    def move(mapping):
        mapping["ties"] = [entry]

    edit(ws, SUBCATEGORY_MAPPING_PATH, move)
    _refused_naming(ws, TIE)
