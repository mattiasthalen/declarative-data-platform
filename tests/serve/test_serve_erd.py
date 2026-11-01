"""Serve's diagram in the README's erd:serve region (story #3: AC4, EC10).

Runs ``uv run serve generate`` in a copy of the repo, without a dbt build, and reads the region
back. The interface assumed (markers, the erDiagram's shape) is set out in ``tests/erd.py``.
"""

from __future__ import annotations

import erd
import pytest
from erd import PR_ATTRIBUTES
from harness import require


@pytest.fixture(scope="module")
def shared(make_workspace, tmp_path_factory):
    ws = make_workspace("erd-serve")
    require(ws.generate())
    return erd.keep(ws, tmp_path_factory.mktemp("erd-serve-pristine"))


@pytest.fixture
def ws(shared):
    return erd.restore(*shared)


def relationship(entity: str) -> str:
    return f'_bridge }}o--|| {entity} : "_key__{entity}"'


def keys(shown: erd.Diagram, entity: str) -> dict[str, str | None]:
    return {name: key for _, name, key, _ in shown.rows(entity)}


def test_erd_serve(ws):
    """AC4: `product` with its key (PK), valid-from, valid-to and the seven attribute columns in model
    order, each typed by its dataRange; `_bridge` with stage, `_key__product` (FK), `_valid_from`,
    `_valid_to`; one relationship from `_bridge` to `product`; no staged bridge."""
    erd.ok(erd.generate(ws, "serve"))
    shown = erd.layer_diagram(ws, "serve")
    assert list(shown.entities) == ["product", "_bridge"], shown.lines
    assert not any(name.startswith("bridge__") for name in shown.entities), shown.lines

    assert shown.columns("product") == ["_key__product", "product__valid_from", "product__valid_to"] + [
        column for _, _, column in PR_ATTRIBUTES
    ], "\n".join(shown.lines)
    assert keys(shown, "product")["_key__product"] == "PK", "\n".join(shown.lines)
    types = {name: kind for kind, name, _, _ in shown.rows("product")}
    for _, kind, column in PR_ATTRIBUTES:
        assert types[column] == kind, f"{column} is typed {types[column]}, its dataRange is {kind}"

    assert shown.columns("_bridge") == ["stage", "_key__product", "_valid_from", "_valid_to"], "\n".join(shown.lines)
    assert keys(shown, "_bridge")["_key__product"] == "FK", "\n".join(shown.lines)
    assert shown.relationships == [relationship("product")], shown.relationships


def test_erd_serve_two_anchors(ws):
    """EC10: with a second anchor declared first, two dimensions and two relationships from
    `_bridge`, in model order, the bridge after the dimensions."""
    erd.add_vendor_anchor_first(ws)
    erd.ok(erd.generate(ws, "serve"))
    shown = erd.layer_diagram(ws, "serve")
    assert list(shown.entities) == ["vendor", "product", "_bridge"], shown.lines
    assert shown.columns("vendor") == ["_key__vendor", "vendor__valid_from", "vendor__valid_to", "vendor__name"], (
        "\n".join(shown.lines)
    )
    assert shown.columns("_bridge") == ["stage", "_key__vendor", "_key__product", "_valid_from", "_valid_to"], (
        "\n".join(shown.lines)
    )
    bridge = keys(shown, "_bridge")
    assert bridge["_key__vendor"] == bridge["_key__product"] == "FK", "\n".join(shown.lines)
    assert shown.relationships == [relationship("vendor"), relationship("product")], shown.relationships
