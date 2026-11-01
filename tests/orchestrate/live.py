"""The helpers behind the orchestrate fixtures: the Prefect REST API and the fake commands."""

from __future__ import annotations

import json
import socket
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pytest

from harness import Workspace, tail

PREFECT = "prefect>=3.9,<3.10"
POOL = "orchestrate-test-pool"
FAKE = Path(__file__).with_name("fake.py")

TERMINAL = {"COMPLETED", "FAILED", "CANCELLED", "CRASHED"}
NOT_TERMINAL = ["SCHEDULED", "PENDING", "RUNNING", "PAUSED", "CANCELLING"]

# The waits are hard caps, so a red run ends in minutes rather than hanging.
SERVER_UP_SECONDS = 120
WORKER_UP_SECONDS = 120
DEPLOY_SECONDS = 600
RUN_SECONDS = 180


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def when(timestamp: str | None) -> float | None:
    return None if timestamp is None else datetime.fromisoformat(timestamp).timestamp()


@dataclass
class Prefect:
    """A live Prefect server with the repo's deployments, seen through its REST API."""

    api: str
    ws: Workspace
    env: dict[str, str]
    logs: Path
    problem: str | None = None
    _deployments: dict[str, dict] = field(default_factory=dict)

    # -- the API

    def call(self, method: str, path: str, body: dict | None = None):
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(
            self.api + path, data=data, method=method, headers={"Content-Type": "application/json"}
        )
        # SQLite under a busy server answers 503 now and then; Prefect's own clients retry it too.
        for attempt in range(6):
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    text = response.read().decode()
                return json.loads(text) if text else None
            except urllib.error.HTTPError as e:
                if e.code == 503 and attempt < 5:
                    time.sleep(1 + attempt)
                    continue
                raise AssertionError(f"{method} {path} -> {e.code}: {e.read().decode()[:2000]}") from e

    def worker_log(self) -> str:
        path = self.logs / "worker.log"
        return tail(path.read_text(errors="replace"), 4000) if path.exists() else "(no worker log)"

    # -- deployments

    def deployed(self) -> None:
        """Fail the calling test unless the three deployments are on the server."""
        if self.problem:
            pytest.fail(self.problem, pytrace=False)

    def deployment(self, name: str) -> dict:
        """``run``, ``ingest-source`` or ``build``: the deployment ``<name>/<name>``."""
        self.deployed()
        if name not in self._deployments:
            self._deployments[name] = self.call("GET", f"/deployments/name/{name}/{name}")
        return self._deployments[name]

    def trigger(self, name: str, parameters: dict) -> str:
        run = self.call(
            "POST",
            f"/deployments/{self.deployment(name)['id']}/create_flow_run",
            {"parameters": parameters},
        )
        return run["id"]

    # -- flow runs

    def flow_run(self, run_id: str) -> dict:
        return self.call("GET", f"/flow_runs/{run_id}")

    def state(self, run_id: str) -> tuple[str, str, str]:
        """(type, name, message) of the run's current state."""
        state = self.flow_run(run_id)["state"] or {}
        return state.get("type", ""), state.get("name", ""), state.get("message") or ""

    def wait(self, run_id: str, seconds: float = RUN_SECONDS, until: str | None = None) -> dict:
        """The run once it reaches state type ``until``, or any terminal state when ``until`` is None.

        Fails the test after ``seconds``, or when the run ends without reaching ``until``.
        """
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            run = self.flow_run(run_id)
            kind = (run["state"] or {}).get("type")
            if kind == until or (until is None and kind in TERMINAL):
                return run
            if kind in TERMINAL:
                pytest.fail(f"flow run {run['name']} ended {run['state']} before reaching {until}")
            time.sleep(0.5)
        run = self.flow_run(run_id)
        pytest.fail(
            f"flow run {run['name']} still {run['state']} after {seconds}s, "
            f"waiting for {until or 'a terminal state'}.\n"
            f"Worker log:\n{self.worker_log()}",
            pytrace=False,
        )

    def runs(self, flow_runs: dict) -> list[dict]:
        return self.call("POST", "/flow_runs/filter", {"flow_runs": flow_runs, "limit": 200})

    def children(self, run_id: str, deployment: str | None = None) -> list[dict]:
        """The flow runs started from inside ``run_id``, of one deployment or of any."""
        found = self.runs({"parent_flow_run_id": {"any_": [run_id]}})
        if deployment is not None:
            found = [r for r in found if r["deployment_id"] == self.deployment(deployment)["id"]]
        return found

    def cancel_unfinished(self) -> None:
        """Ask every run not yet terminal to cancel, so one test's leftovers hold no slot."""
        pending = self.runs({"state": {"type": {"any_": NOT_TERMINAL}}})
        for run in pending:
            # A run no worker holds yet is cancelled outright; one a worker runs is killed by it.
            to = "CANCELLED" if run["state"]["type"] in ("SCHEDULED", "PAUSED") else "CANCELLING"
            try:
                self.call(
                    "POST",
                    f"/flow_runs/{run['id']}/set_state",
                    {"state": {"type": to, "message": "test cleanup"}, "force": True},
                )
            except AssertionError:
                pass
        deadline = time.monotonic() + 45
        while pending and time.monotonic() < deadline:
            pending = self.runs({"state": {"type": {"any_": NOT_TERMINAL}}})
            time.sleep(1)


@dataclass
class Fakes:
    """One test's fake commands and their call logs."""

    dir: Path
    python: str = sys.executable

    def _spec(self, name: str, spec: dict) -> str:
        path = self.dir / f"{name}-{len(list(self.dir.glob('*.json')))}.json"
        path.write_text(json.dumps(spec))
        return str(path)

    def _fake(self, *args: str) -> list[str]:
        return [self.python, str(FAKE), *args]

    def list_command(self, *sources: str, stdout: str | None = None, exit: int = 0, stderr: str = "") -> list[str]:
        out = stdout if stdout is not None else "".join(f"{s}\n" for s in sources)
        return self._fake("list", self._spec("list", {"stdout": out, "stderr": stderr, "exit": exit}))

    def ingest_command(self, behaviour: dict[str, object] | None = None, log: str = "ingest") -> list[str]:
        return self._fake("ingest", self._spec(f"{log}-table", behaviour or {}), str(self.dir / f"{log}.log"))

    def lake_command(self, log: str = "ingest") -> list[str]:
        return self._fake("lake", str(self.dir / f"{log}.log"))

    def build_command(
        self, exit: int = 0, sleep: float = 0, log: str = "build", pidfile: Path | None = None
    ) -> list[str]:
        behaviour: dict[str, object] = {"exit": exit, "sleep": sleep}
        if pidfile is not None:
            behaviour["pidfile"] = str(pidfile)
        spec = self._spec(f"{log}-spec", behaviour)
        return self._fake("build", spec, str(self.dir / f"{log}.log"))

    def calls(self, log: str) -> list[dict]:
        path = self.dir / f"{log}.log"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
