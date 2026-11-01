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

from prefect import flow, get_run_logger
from prefect.client.schemas.objects import FlowRun
from prefect.deployments import run_deployment
from prefect.states import Completed, Failed, State

LIST_COMMAND = ["uv", "run", "task", "ingest:list"]
# `-x` passes the command's own exit status through; without it go-task reports every
# failure as 201, and a partial landing (1) could not be told from none (2).
INGEST_COMMAND = ["uv", "run", "task", "-x", "ingest:source", "--"]
BUILD_COMMAND = ["uv", "run", "task", "-x", "build"]
INGEST_TIMEOUT_SECONDS = 20 * 60
BUILD_TIMEOUT_SECONDS = 30 * 60

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


def run_command(command: list[str], timeout: float | None = None) -> Outcome:
    """Run ``command`` without a shell, from the current directory.

    Past ``timeout`` the whole process group is killed: `uv run task` starts grandchildren
    (task, dlt, dbt) that killing `uv` alone would leave running.
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
    state = child.state
    return state is not None and (state.is_completed() or state.name == PARTLY_LANDED)


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
    listing = await asyncio.to_thread(run_command, list_command)
    if listing.exit != 0:
        return Failed(
            message=f"listing the sources failed (exit {listing.exit}): {listing.stderr.strip()}"
        )
    sources = list(dict.fromkeys(line.strip() for line in listing.stdout.splitlines() if line.strip()))
    if not sources:
        return Failed(message="no sources listed: nothing to ingest")

    children = await asyncio.gather(
        *(
            run_deployment(
                "ingest-source/ingest-source",
                parameters={
                    "source": source,
                    "command": ingest_command,
                    "timeout_seconds": ingest_timeout_seconds,
                },
                timeout=None,
                as_subflow=True,
            )
            for source in sources
        )
    )
    failed = [source for source, child in zip(sources, children) if not child.state.is_completed()]
    problems = [f"sources not fully landed: {', '.join(failed)}"] if failed else []

    if not any(landed(child) for child in children):
        return Failed(message="; ".join(problems) + "; no source landed, so no build")

    built = await run_deployment(
        "build/build",
        parameters={"target": target, "command": build_command, "timeout_seconds": build_timeout_seconds},
        timeout=None,
        as_subflow=True,
    )
    if not built.state.is_completed():
        problems.append(f"build {built.state.name}: {built.state.message}")
    if problems:
        return Failed(message="; ".join(problems))
    return Completed(message=f"{len(sources)} sources landed, {target} built")
