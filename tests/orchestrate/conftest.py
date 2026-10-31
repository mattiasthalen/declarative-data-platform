"""The Prefect side of the story #16 tests: one server, one process worker, one deploy per session.

The infra the spec leaves outside the repo is brought up here, the way an environment would:

- a Prefect server on a free local port with its own throwaway ``PREFECT_HOME`` and SQLite
  database. Its scheduler service is off, so the hourly schedule is declared and active but
  never fires a real ``task ingest:list`` mid-session; the deployment-concurrency retry wait
  is shortened so a queued ``build`` is retried within seconds;
- a process work pool, named through ``ORCHESTRATE_WORK_POOL``, and a worker on it started
  from the root of a throwaway copy of the repo (``harness.Workspace``);
- ``prefect deploy --all --prefect-file orchestrate/prefect.yaml`` from that root.

Tests trigger deployments through the REST API with each command parameter pointed at
``fake.py``, and read back what an operator would: flow runs, their parents, states, state
messages and times, plus the fakes' call logs. A deploy that fails does not error the
fixture: every test that needs the deployments fails with what went wrong.
"""

from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path

import pytest

from harness import tail

from .live import (
    DEPLOY_SECONDS,
    POOL,
    PREFECT,
    SERVER_UP_SECONDS,
    WORKER_UP_SECONDS,
    Fakes,
    Prefect,
    declares_prefect,
    free_port,
)


def start(args: list[str], *, cwd: Path, env: dict[str, str], log: Path) -> subprocess.Popen:
    out = open(log, "w")
    return subprocess.Popen(
        args, cwd=cwd, env=env, stdout=out, stderr=subprocess.STDOUT, start_new_session=True
    )


def stop(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(timeout=20)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


@pytest.fixture(scope="session")
def prefect(make_workspace, tmp_path_factory):
    """The session's Prefect server and worker, and the repo's deployments on them."""
    ws = make_workspace("orchestrate")
    home = tmp_path_factory.mktemp("prefect")
    logs = home / "logs"
    logs.mkdir()
    port = free_port()
    api = f"http://127.0.0.1:{port}/api"

    server_env = {
        k: v for k, v in os.environ.items() if not k.startswith("PREFECT_") and k != "VIRTUAL_ENV"
    }
    server_env.update(
        PREFECT_HOME=str(home / "server-home"),
        PREFECT_API_DATABASE_CONNECTION_URL=f"sqlite+aiosqlite:///{home / 'prefect.db'}",
        PREFECT_SERVER_SERVICES_SCHEDULER_ENABLED="false",
        PREFECT_SERVER_DEPLOYMENTS_CONCURRENCY_SLOT_WAIT_SECONDS="2",
        PREFECT_SERVER_ANALYTICS_ENABLED="false",
        PREFECT_UI_ENABLED="false",
        PREFECT_SERVER_UI_ENABLED="false",
        DO_NOT_TRACK="1",
    )
    server = start(
        ["uv", "run", "--no-project", "--with", PREFECT, "prefect", "server", "start",
         "--host", "127.0.0.1", "--port", str(port)],
        cwd=home, env=server_env, log=logs / "server.log",
    )

    # What the repo sees: the infra's server and pool, from the environment.
    env = {k: v for k, v in ws.env().items() if not k.startswith("PREFECT_")}
    env.update(
        PREFECT_API_URL=api,
        PREFECT_HOME=str(home / "client-home"),
        ORCHESTRATE_WORK_POOL=POOL,
        # As a shell started in the repo root would have it; a deploy may template it.
        PWD=str(ws.root),
        PREFECT_WORKER_QUERY_SECONDS="1",
        PREFECT_SERVER_ANALYTICS_ENABLED="false",
        DO_NOT_TRACK="1",
    )
    uv_run = ["uv", "run"] if declares_prefect(ws.root) else ["uv", "run", "--with", PREFECT]
    p = Prefect(api=api, ws=ws, env=env, logs=logs)
    worker = None
    try:
        deadline = time.monotonic() + SERVER_UP_SECONDS
        while True:
            try:
                p.call("GET", "/health")
                break
            except (OSError, AssertionError):
                if server.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError(
                        "the Prefect server did not start:\n"
                        + tail((logs / "server.log").read_text(errors="replace"))
                    )
                time.sleep(1)

        pool = subprocess.run(
            ["uv", "run", "--no-project", "--with", PREFECT, "prefect", "work-pool", "create",
             POOL, "--type", "process"],
            cwd=home, env={**server_env, "PREFECT_API_URL": api, "PREFECT_HOME": str(home / "client-home")},
            capture_output=True, text=True, timeout=SERVER_UP_SECONDS,
        )
        if pool.returncode != 0:
            raise RuntimeError(f"could not create the work pool:\n{tail(pool.stdout + pool.stderr)}")
        worker = start(
            [*uv_run, "prefect", "worker", "start", "--pool", POOL, "--type", "process"],
            cwd=ws.root, env=env, log=logs / "worker.log",
        )
        deadline = time.monotonic() + WORKER_UP_SECONDS
        while not any(
            w.get("status") == "ONLINE"
            for w in p.call("POST", f"/work_pools/{POOL}/workers/filter", {})
        ):
            if worker.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError(f"the process worker did not come online:\n{p.worker_log()}")
            time.sleep(1)

        declaration = ws.root / "orchestrate" / "prefect.yaml"
        if not declaration.exists():
            p.problem = "orchestrate/prefect.yaml does not exist in the repo: nothing to deploy"
        else:
            deploy = subprocess.run(
                [*uv_run, "prefect", "--no-prompt", "deploy", "--all",
                 "--prefect-file", "orchestrate/prefect.yaml"],
                cwd=ws.root, env=env, capture_output=True, text=True, timeout=DEPLOY_SECONDS,
            )
            if deploy.returncode != 0:
                p.problem = (
                    f"`prefect deploy --all --prefect-file orchestrate/prefect.yaml` exited "
                    f"{deploy.returncode}:\n{tail(deploy.stdout + deploy.stderr)}"
                )
            else:
                missing = []
                for name in ("run", "ingest-source", "build"):
                    try:
                        p.call("GET", f"/deployments/name/{name}/{name}")
                    except AssertionError as e:
                        missing.append(f"{name}/{name}: {e}")
                if missing:
                    p.problem = "deployed, but not every deployment is on the server:\n" + "\n".join(missing)
        if not p.problem:
            # No run may start that a test did not trigger.
            p.cancel_unfinished()
        yield p
    finally:
        if worker is not None:
            try:
                p.cancel_unfinished()
            except Exception:
                pass
            stop(worker)
        stop(server)


@pytest.fixture
def fakes(tmp_path) -> Fakes:
    return Fakes(tmp_path)


@pytest.fixture
def orchestrated(prefect):
    """``prefect``, with no run left unfinished after the test.

    Tests reach the deployments through ``Prefect.deployment``, which fails the test itself
    (not its setup) when the deploy did not happen.
    """
    yield prefect
    prefect.cancel_unfinished()
