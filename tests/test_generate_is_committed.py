"""The committed generated output is exactly what the generators write (story 2, AC14).

`task check` on a clean clone of the committed repo exits 0, so drift fails here naming the
file rather than as an unexplained `git status`.
"""

from __future__ import annotations

import subprocess

from harness import REPO, Workspace, require, tail


def test_generate_is_committed(tmp_path):
    """AC14: `task check` exits 0 on a clean clone of HEAD."""
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "--quiet", str(REPO), str(clone)], check=True)
    head = subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    )
    subprocess.run(["git", "-C", str(clone), "checkout", "--quiet", head.stdout.strip()], check=True)
    ws = Workspace(clone)
    require(ws.sync())
    step = ws.run("uv", "run", "task", "check")
    assert step.returncode == 0, f"`task check` found drift on a clean clone:\n{tail(step.output)}"
