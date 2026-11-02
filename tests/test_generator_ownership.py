"""Generators own only package folders that carry their marker README.md (AC20, EC9).

Each test runs a layer's generator, ``uv run <layer> generate``, in its own copy of the repo.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

import ownership
from harness import CONTRACT, CONTRACT_PATH, Workspace, require


def packages(ws: Workspace, layer: str) -> list[Path]:
    """The package folders under models/<layer>/ that carry a marker README.md."""
    found = sorted(p.parent for p in (ws.root / "models" / layer).glob("*/README.md"))
    assert found, f"models/{layer}/ has no marked package folder"
    return found


def products_package(ws: Workspace) -> Path:
    found = packages(ws, "conform")
    return next((p for p in found if "product" in p.name.lower()), found[0])


def generate(ws: Workspace, layer: str):
    return ws.run("uv", "run", layer, "generate")


@pytest.fixture
def ws(make_workspace) -> Workspace:
    return make_workspace("ownership")


def test_stale_file_removed(ws):
    """AC20: a file the generator did not write is removed from its own marked folder."""
    folder = products_package(ws)
    stale = folder / "zz_stale_model.sql"
    stale.write_text("select 1 as stale\n")
    require(generate(ws, "conform"))
    assert not stale.exists()
    assert (folder / "README.md").exists()


def test_refuses_unmarked_folder(ws):
    """AC20: a folder it would write with no marker is refused: non-zero exit, nothing written."""
    folder = products_package(ws)
    (folder / "README.md").unlink()
    before = ws.tree()
    step = generate(ws, "conform")
    assert step.returncode != 0, step.output
    assert ws.tree() == before


def test_refuses_another_generators_folder(ws):
    """AC20: a folder carrying another generator's marker is refused: non-zero exit, nothing written."""
    folder = products_package(ws)
    shutil.copyfile(packages(ws, "integrate")[0] / "README.md", folder / "README.md")
    before = ws.tree()
    step = generate(ws, "conform")
    assert step.returncode != 0, step.output
    assert ws.tree() == before


def test_removed_contract_removes_its_files(ws):
    """EC9: removing a contract makes the next generate delete its generated files."""
    folder = products_package(ws)
    (ws.root / CONTRACT_PATH).unlink()
    require(generate(ws, "conform"))
    left = [p.name for p in folder.glob("*") if p.name != "README.md"] if folder.exists() else []
    assert left == []
    named = [
        p.relative_to(ws.root).as_posix() for p in (ws.root / "models").rglob(f"*{CONTRACT}*") if p.is_file()
    ]
    assert named == []


def _prune(node, gone: set[str]):
    """Drop every mapping key, and every list item, that names an attribute in ``gone``."""

    def names(value) -> bool:
        return isinstance(value, str) and (value in gone or value.startswith("PR_DIS"))

    def mentions(value) -> bool:
        if isinstance(value, dict):
            return any(names(k) or names(v) for k, v in value.items() if not isinstance(v, (dict, list)))
        return names(value)

    if isinstance(node, dict):
        return {k: _prune(v, gone) for k, v in node.items() if not names(k)}
    if isinstance(node, list):
        return [_prune(item, gone) for item in node if not mentions(item)]
    return node


def test_removed_attribute_removes_its_files(ws):
    """EC9: removing an attribute (DIS) from the model and its mapping makes integrate generate delete its files."""
    gone = {"DIS", "Discontinued"}
    for path in (ws.root / "anchor" / "model.yaml", ws.root / "anchor" / "mappings" / "PR_Product.yaml"):
        document = _prune(yaml.safe_load(path.read_text()), gone)
        path.write_text(yaml.safe_dump(document, sort_keys=False, allow_unicode=True))
    assert "PR_DIS" in "".join(
        p.name + p.read_text() for p in (ws.root / "models" / "integrate").rglob("*") if p.is_file()
    )
    require(generate(ws, "integrate"))
    leftover = [
        p.relative_to(ws.root).as_posix()
        for p in (ws.root / "models" / "integrate").rglob("*")
        if p.is_file() and "PR_DIS" in p.name + p.read_text()
    ]
    assert leftover == []


def test_root_folder_no_longer_written_is_stale(tmp_path):
    """AC2: a folder at the repo root that a generator owns but no longer writes is stale; one another generator owns is not."""
    for folder, generator in (("assets", "artwork"), ("diagrams", "erd")):
        (tmp_path / folder).mkdir()
        (tmp_path / folder / "README.md").write_text(ownership.marker(generator, "test declarations"))
    drifts = ownership.drift(tmp_path, "artwork", "test declarations", {Path("art"): {"hero.svg": "<svg/>\n"}})
    stale = [d.path.as_posix() for d in drifts if d.kind == "stale"]
    assert stale == ["assets"]
