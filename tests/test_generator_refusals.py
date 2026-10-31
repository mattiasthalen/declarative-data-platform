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

from harness import CONTRACT, CONTRACT_PATH, Workspace, require

MODEL_PATH = "anchor/model.yaml"
MAPPING_PATH = "anchor/mappings/PR_Product.yaml"


@pytest.fixture(scope="module")
def shared(make_workspace) -> Workspace:
    return make_workspace("refusals")


@pytest.fixture
def ws(shared):
    paths = (CONTRACT_PATH, MODEL_PATH, MAPPING_PATH)
    originals = {p: (shared.root / p).read_text() for p in paths}
    yield shared
    for p, text in originals.items():
        (shared.root / p).write_text(text)
    require(shared.generate())


def edit(ws: Workspace, path: str, change: Callable[[dict], None]) -> None:
    file = ws.root / path
    document = yaml.safe_load(file.read_text())
    change(document)
    file.write_text(yaml.safe_dump(document, sort_keys=False, allow_unicode=True))


def refused(ws: Workspace, layer: str) -> None:
    before = ws.tree()
    step = ws.run("uv", "run", layer, "generate")
    assert step.returncode != 0, f"{layer} generate accepted it:\n{step.output[-3000:]}"
    after = ws.tree()
    written = sorted(
        p for p in set(before) | set(after) if p.startswith("models/") and before.get(p) != after.get(p)
    )
    assert written == [], f"{layer} generate wrote while refusing: {written}"


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
    return model["schema"]["anchor"][0]


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
