"""Story #5 AC7: the integrate generator writes the time-traveling perspective t<anchor> for every anchor.

The end-to-end tests (``test_tt_*``) hold what the macro returns; these hold that it is generated.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from harness import REPO, require

INTEGRATE = REPO / "models" / "integrate"
CONFIG = re.compile(r"\{\{\s*config\((?P<args>.*?)\)\s*\}\}", re.DOTALL)
PARAMETERS = re.compile(r"parameters\s*=\s*\[(?P<names>[^\]]*)\]")


def anchors() -> list[str]:
    """``<mnemonic>_<descriptor>`` of every anchor in anchor/model.yaml."""
    model = yaml.safe_load((REPO / "anchor" / "model.yaml").read_text(encoding="utf-8"))
    found = model["schema"]["anchor"]
    found = found if isinstance(found, list) else [found]
    return [f"{a['mnemonic']}_{a['descriptor']}" for a in found]


def macro(folder: Path, name: str) -> Path:
    found = sorted(folder.rglob(f"{name}.sql"))
    assert len(found) == 1, f"{folder.relative_to(REPO)} holds {len(found)} files named {name}.sql"
    return found[0]


def config(path: Path) -> tuple[str, list[str]]:
    """(materialization, parameter names in order) of a model's config call."""
    found = CONFIG.search(path.read_text(encoding="utf-8"))
    assert found, f"{path.name} has no config call"
    args = found.group("args")
    materialized = re.search(r"materialized\s*=\s*['\"](\w+)['\"]", args)
    parameters = PARAMETERS.search(args)
    names = re.findall(r"['\"](\w+)['\"]", parameters.group("names")) if parameters else []
    return (materialized.group(1) if materialized else ""), names


def test_tt_generated_for_every_anchor():
    """AC7: for every anchor, the committed t<anchor>.sql is a table macro taking changingTimepoint and
    positingTimepoint, in that order; p<anchor>.sql still takes changingTimepoint alone (ADR-0030)."""
    names = anchors()
    assert names, "anchor/model.yaml declares no anchor"
    for name in names:
        assert config(macro(INTEGRATE, f"t{name}")) == ("table_macro", ["changingTimepoint", "positingTimepoint"]), name
        assert config(macro(INTEGRATE, f"p{name}")) == ("table_macro", ["changingTimepoint"]), name


def test_tt_generated_by_the_generator(make_workspace):
    """AC7: `uv run integrate generate` writes tPR_Product.sql when it is missing, as committed."""
    ws = make_workspace("tt-generated")
    committed = macro(INTEGRATE, "tPR_Product")
    copy = ws.root / committed.relative_to(REPO)
    copy.unlink()
    require(ws.run("uv", "run", "integrate", "generate"))
    assert copy.exists(), f"the generator did not write {copy.relative_to(ws.root)}"
    assert copy.read_text(encoding="utf-8") == committed.read_text(encoding="utf-8")
