"""Integrate's diagram in the README's erd:integrate region (story #3: AC3, EC8).

Runs ``uv run integrate generate`` in a copy of the repo, without a dbt build, and reads the region
back. The interface assumed (markers, the erDiagram's shape) is set out in ``tests/erd.py``.
"""

from __future__ import annotations

import erd
import pytest
from erd import PR_ATTRIBUTES
from harness import require


@pytest.fixture(scope="module")
def shared(make_workspace, tmp_path_factory):
    ws = make_workspace("erd-integrate")
    require(ws.generate())
    return erd.keep(ws, tmp_path_factory.mktemp("erd-integrate-pristine"))


@pytest.fixture
def ws(shared):
    return erd.restore(*shared)


def test_erd_integrate(ws):
    """AC3: PR_Product alone, `int PR_ID PK` then the seven attributes in model order, each typed by
    its dataRange and commented "historized"."""
    erd.ok(erd.generate(ws, "integrate"))
    shown = erd.layer_diagram(ws, "integrate")
    assert list(shown.entities) == ["PR_Product"], shown.lines
    expected = [("int", "PR_ID", "PK", None)] + [(kind, name, None, "historized") for name, kind, _ in PR_ATTRIBUTES]
    assert shown.rows("PR_Product") == expected, "\n".join(shown.lines)


def test_erd_types(ws):
    """EC8: a dataRange with a space, `decimal(10, 2)`, appears as `decimal(10,2)`."""

    def change(model):
        attribute = next(a for a in model["schema"]["anchor"][0]["attribute"] if a["mnemonic"] == "COL")
        attribute["dataRange"] = "decimal(10, 2)"

    erd.edit_yaml(erd.model_path(ws), change)
    erd.ok(erd.generate(ws, "integrate"))
    shown = erd.layer_diagram(ws, "integrate")
    rows = {name: kind for kind, name, _, _ in shown.rows("PR_Product")}
    assert rows.get("PR_COL_Product_Color") == "decimal(10,2)", "\n".join(shown.lines)
