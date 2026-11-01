"""Story #16, review round 1: the real `ingest:source` Taskfile task, without Prefect.

Every name here is undeclared, so ingest refuses it before any request: no network is used.
"""

from __future__ import annotations

import subprocess

from harness import REPO, tail


def ingest_source(name: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["uv", "run", "task", "-x", "ingest:source", "--", name],
        cwd=REPO, capture_output=True, text=True, timeout=300,
    )


def test_ingest_source_name_not_run_by_shell(tmp_path):
    """R2 (a): a name holding `$(...)` exits 2 and runs nothing."""
    pwned = tmp_path / "pwned"
    done = ingest_source(f"x$(touch {pwned})")
    assert not pwned.exists(), "the shell ran `$(touch ...)` from the source name"
    assert done.returncode == 2, f"exited {done.returncode}:\n{tail(done.stdout + done.stderr)}"


def test_ingest_source_name_not_an_option():
    """R2 (b): `--list` is a source name, not ingest's option: exits 2, not 0."""
    done = ingest_source("--list")
    assert done.returncode == 2, f"exited {done.returncode}:\n{tail(done.stdout + done.stderr)}"


def test_ingest_source_exit_passed_through():
    """R2 (c): with -x, an undeclared name exits ingest's own 2, not go-task's 201."""
    done = ingest_source("nosuch")
    assert done.returncode == 2, f"exited {done.returncode}:\n{tail(done.stdout + done.stderr)}"
