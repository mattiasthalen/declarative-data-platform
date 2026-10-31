"""AC5: `task generate` on a clean checkout of the committed repo leaves git status clean."""

from __future__ import annotations

import subprocess

from harness import REPO, Workspace, require


def test_generate_is_committed(tmp_path):
    """AC5: the committed generated output is exactly what the generators write."""
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "--quiet", str(REPO), str(clone)], check=True)
    head = subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    )
    subprocess.run(["git", "-C", str(clone), "checkout", "--quiet", head.stdout.strip()], check=True)
    ws = Workspace(clone)
    require(ws.sync())
    require(ws.generate())
    status = subprocess.run(
        ["git", "-C", str(clone), "status", "--porcelain"], capture_output=True, text=True, check=True
    )
    assert status.stdout == "", status.stdout
