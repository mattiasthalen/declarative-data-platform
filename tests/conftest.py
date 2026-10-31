"""Fixtures shared by every S1 test. The helpers live in ``harness.py``, beside this file."""

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
