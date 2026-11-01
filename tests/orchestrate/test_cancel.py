"""Story #16, review round 1: cancelling a flow run in Prefect stops the command it started.

Prefect's process worker signals the flow run's own process group; the command runs in a
group of its own, so the flow has to stop it.
"""

from __future__ import annotations

import os
import signal
import time
from pathlib import Path

import pytest

from .live import Fakes, Prefect

SOURCE = "src_alpha"
STARTED_SECONDS = 120
GONE_SECONDS = 10


def alive(pid: int) -> bool:
    """Whether ``pid`` is a process that has not exited (a zombie has exited)."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
    except (FileNotFoundError, ProcessLookupError):
        return False
    return stat.rsplit(")", 1)[1].split()[0] != "Z"


def trigger_long(prefect: Prefect, fakes: Fakes, deployment: str, pidfile: Path) -> str:
    if deployment == "build":
        return prefect.trigger("build", {"command": fakes.build_command(sleep=300, pidfile=pidfile)})
    command = fakes.ingest_command({SOURCE: {"sleep": 300, "exit": 0, "pidfile": str(pidfile)}})
    return prefect.trigger("ingest-source", {"source": SOURCE, "command": command})


@pytest.mark.parametrize("deployment", ["build", "ingest-source"])
def test_cancel_stops_command(orchestrated, fakes, deployment):
    """R1: a Running flow run cancelled through the API ends Cancelled and its command's process is gone."""
    pidfile = fakes.dir / "command.pid"
    run = trigger_long(orchestrated, fakes, deployment, pidfile)
    orchestrated.wait(run, until="RUNNING")

    deadline = time.monotonic() + STARTED_SECONDS
    while not (pidfile.exists() and pidfile.read_text().strip()):
        assert time.monotonic() < deadline, (
            f"the fake command never started within {STARTED_SECONDS}s.\n"
            f"Worker log:\n{orchestrated.worker_log()}"
        )
        time.sleep(0.5)
    pid = int(pidfile.read_text())
    assert alive(pid), "the fake command exited before the cancel"

    try:
        orchestrated.call(
            "POST",
            f"/flow_runs/{run}/set_state",
            {"state": {"type": "CANCELLING", "message": "R1: cancelled by the test"}},
        )
        finished = orchestrated.wait(run)
        assert finished["state"]["type"] == "CANCELLED", finished["state"]

        deadline = time.monotonic() + GONE_SECONDS
        while alive(pid) and time.monotonic() < deadline:
            time.sleep(0.25)
        assert not alive(pid), (
            f"`{deployment}` was cancelled, but its command (pid {pid}) is still running "
            f"{GONE_SECONDS}s later"
        )
    finally:
        if alive(pid):
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
