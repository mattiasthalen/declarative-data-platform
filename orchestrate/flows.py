"""The scheduled run, as Prefect flows that only call Taskfile tasks (ADR-0020).

`run` lists the sources, starts one `ingest-source` flow run per source (its own process or
pod on the work pool, ADR-0021), waits for all of them, then starts one `build` flow run if
any source landed something, and ends Failed when anything did not land (ADR-0022).
`orchestrate/prefect.yaml` declares the deployments, the schedule and the concurrency limits.
"""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
from dataclasses import dataclass

from prefect import flow, get_client, get_run_logger
from prefect.client.schemas.objects import FlowRun
from prefect.deployments import run_deployment
from prefect.states import Cancelled, Completed, Failed, State

LIST_COMMAND = ["uv", "run", "task", "ingest:list"]
# `-x` passes the command's own exit status through; without it go-task reports every
# failure as 201, and a partial landing (1) could not be told from none (2).
INGEST_COMMAND = ["uv", "run", "task", "-x", "ingest:source", "--"]
BUILD_COMMAND = ["uv", "run", "task", "-x", "build"]
LIST_TIMEOUT_SECONDS = 5 * 60
INGEST_TIMEOUT_SECONDS = 20 * 60
BUILD_TIMEOUT_SECONDS = 30 * 60
# How long `run` waits beyond a child's own timeout for it to reach a final state. A child
# that never starts (no free worker, a pool limit `run` itself fills) would otherwise hold
# `run`, and with it the deployment's only concurrency slot, for good.
START_GRACE_SECONDS = 10 * 60

# Ingest's exit statuses (ADR-0018): 0 every resource landed, 1 some did, 2 none.
LANDED_ALL, LANDED_SOME = 0, 1
# The name an `ingest-source` run's Failed state carries when some resources landed, which is
# how `run` tells a partial landing from none at all.
PARTLY_LANDED = "Partly landed"


@dataclass
class Outcome:
    exit: int | None  # None: the command ran past its timeout and was killed
    stdout: str
    stderr: str


def run_command(command: list[str], timeout: float) -> Outcome:
    """Run ``command`` without a shell, from the current directory.

    The command gets its own process group, killed whole past ``timeout`` and whenever the
    flow is interrupted: `uv run task` starts grandchildren (task, dlt, dbt), and Prefect's
    cancellation signals only the flow's own group, so a cancelled build would otherwise
    leave dbt running and holding the DuckDB file.
    """
    proc = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        stdout, stderr = proc.communicate()
        return Outcome(None, stdout, stderr)
    except BaseException:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait()
        raise
    return Outcome(proc.returncode, stdout, stderr)


def echo(outcome: Outcome) -> None:
    logger = get_run_logger()
    for line in outcome.stdout.splitlines():
        logger.info(line)
    for line in outcome.stderr.splitlines():
        logger.warning(line)


@flow(name="ingest-source")
def ingest_source(
    source: str,
    command: list[str] = INGEST_COMMAND,
    timeout_seconds: float = INGEST_TIMEOUT_SECONDS,
) -> State:
    """Land one source's resources, the source name appended to ``command`` as one argument."""
    outcome = run_command([*command, source], timeout_seconds)
    echo(outcome)
    if outcome.exit is None:
        return Failed(message=f"{source} timed out after {timeout_seconds:g}s")
    if outcome.exit == LANDED_ALL:
        return Completed(message=f"{source} landed")
    if outcome.exit == LANDED_SOME:
        return Failed(name=PARTLY_LANDED, message=f"{source} landed some resources (exit 1)")
    return Failed(message=f"{source} landed nothing (exit {outcome.exit})")


@flow(name="build")
def build(
    target: str = "prod",
    command: list[str] = BUILD_COMMAND,
    timeout_seconds: float = BUILD_TIMEOUT_SECONDS,
) -> State:
    """Build ``target``, `TARGET=<target>` appended to ``command`` as one argument."""
    outcome = run_command([*command, f"TARGET={target}"], timeout_seconds)
    echo(outcome)
    if outcome.exit is None:
        return Failed(message=f"the build timed out after {timeout_seconds:g}s")
    if outcome.exit != 0:
        return Failed(message=f"the build failed (exit {outcome.exit})")
    return Completed(message=f"built {target}")


def landed(child: FlowRun) -> bool:
    return child.state.is_completed() or child.state.name == PARTLY_LANDED


async def run_child(deployment: str, parameters: dict, timeout_seconds: float) -> FlowRun:
    """Start a flow run of ``deployment`` under the current flow and wait for it to end.

    One still not final after its own timeout plus START_GRACE_SECONDS is cancelled, and
    returned as it then stands, not final, so the caller counts it as failed.
    """
    child = await run_deployment(
        deployment,
        parameters={**parameters, "timeout_seconds": timeout_seconds},
        timeout=timeout_seconds + START_GRACE_SECONDS,
        as_subflow=True,
    )
    if not child.state.is_final():
        async with get_client() as client:
            await client.set_flow_run_state(
                child.id, Cancelled(message="never finished within its timeout"), force=True
            )
            child = await client.read_flow_run(child.id)
    return child


@flow(name="run")
async def run(
    list_command: list[str] = LIST_COMMAND,
    ingest_command: list[str] = INGEST_COMMAND,
    ingest_timeout_seconds: float = INGEST_TIMEOUT_SECONDS,
    build_command: list[str] = BUILD_COMMAND,
    target: str = "prod",
    build_timeout_seconds: float = BUILD_TIMEOUT_SECONDS,
) -> State:
    """One scheduled run: every source ingested in its own flow run, then one build."""
    listing = await asyncio.to_thread(run_command, list_command, LIST_TIMEOUT_SECONDS)
    if listing.exit is None:
        return Failed(message=f"listing the sources timed out after {LIST_TIMEOUT_SECONDS}s")
    if listing.exit != 0:
        return Failed(
            message=f"listing the sources failed (exit {listing.exit}): {listing.stderr.strip()}"
        )
    sources = list(dict.fromkeys(line.strip() for line in listing.stdout.splitlines() if line.strip()))
    if not sources:
        return Failed(message="no sources listed: nothing to ingest")

    children = await asyncio.gather(
        *(
            run_child(
                "ingest-source/ingest-source",
                {"source": source, "command": ingest_command},
                ingest_timeout_seconds,
            )
            for source in sources
        )
    )
    failed = [source for source, child in zip(sources, children) if not child.state.is_completed()]
    problems = [f"sources not fully landed: {', '.join(failed)}"] if failed else []

    if not any(landed(child) for child in children):
        return Failed(message="; ".join(problems) + "; no source landed, so no build")

    built = await run_child(
        "build/build", {"target": target, "command": build_command}, build_timeout_seconds
    )
    if not built.state.is_completed():
        problems.append(f"build {built.state.name}: {built.state.message}")
    if problems:
        return Failed(message="; ".join(problems))
    return Completed(message=f"{len(sources)} sources landed, {target} built")
