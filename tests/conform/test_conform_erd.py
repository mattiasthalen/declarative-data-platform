"""Conform's diagram in the README's erd:conform region (story #3: AC2, EC9).

Runs ``uv run conform generate`` in a copy of the repo, without a dbt build, and reads the region
back. The interface assumed (markers, the erDiagram's shape) is set out in ``tests/erd.py``.
"""

from __future__ import annotations

import erd
import pytest
from harness import CONTRACT, require


@pytest.fixture(scope="module")
def shared(make_workspace, tmp_path_factory):
    ws = make_workspace("erd-conform")
    require(ws.generate())
    return erd.keep(ws, tmp_path_factory.mktemp("erd-conform-pristine"))


@pytest.fixture
def ws(shared):
    return erd.restore(*shared)


def test_erd_conform(ws):
    """AC2: one entity, adventure_works__products, with exactly one row: `bigint product_id PK`."""
    erd.ok(erd.generate(ws, "conform"))
    shown = erd.layer_diagram(ws, "conform")
    assert list(shown.entities) == [CONTRACT], shown.lines
    assert shown.rows(CONTRACT) == [("bigint", "product_id", "PK", None)], shown.lines
    assert shown.relationships == [], shown.lines


def test_erd_conform_contract_without_primary_key(ws):
    """EC9: a contract with no primaryKey property appears with no rows, its name on a line of its own;
    entities follow the contracts' file names, as conform reads them."""
    name = erd.add_contract(ws, "customers", primary_key=False)
    erd.ok(erd.generate(ws, "conform"))
    shown = erd.layer_diagram(ws, "conform")
    assert list(shown.entities) == [name, CONTRACT], shown.lines
    assert shown.entities[name] is None, f"{name} is not a bare entity on a line of its own:\n" + "\n".join(shown.lines)
    assert shown.rows(CONTRACT) == [("bigint", "product_id", "PK", None)], shown.lines
