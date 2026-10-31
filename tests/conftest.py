"""Fixtures shared by every S1 test. The helpers live in ``harness.py``, beside this file."""

import re
import shutil

import pytest

from harness import NOT_IN_A_CLONE, REPO, Workspace, require


@pytest.fixture(scope="session")
def make_workspace(tmp_path_factory):
    """Factory: a fresh copy of the repo (synced, empty lake folder, no warehouse)."""

    def make(label: str, *, sync: bool = True) -> Workspace:
        root = tmp_path_factory.mktemp(label) / "repo"
        shutil.copytree(REPO, root, ignore=NOT_IN_A_CLONE, symlinks=True)
        ws = Workspace(root)
        ws.lake.mkdir()
        if sync:
            require(ws.sync())
        return ws

    return make


def _names_claude_positively(markexpr: str) -> bool:
    """True when ``-m`` names ``claude`` other than as ``not claude``."""
    return any(
        not re.search(r"\bnot\s*\(?\s*$", markexpr[: match.start()])
        for match in re.finditer(r"\bclaude\b", markexpr)
    )


def pytest_collection_modifyitems(config, items):
    """AC8, AC12: the live tests run only when ``-m`` asks for ``claude`` by name.

    An ``addopts -m 'not claude'`` would not do: pytest keeps only the last ``-m``, so
    ``-m "not e2e"`` would bring the live tests back.
    """
    if _names_claude_positively(config.option.markexpr or ""):
        return
    live = [item for item in items if item.get_closest_marker("claude")]
    if live:
        items[:] = [item for item in items if not item.get_closest_marker("claude")]
        config.hook.pytest_deselected(items=live)
