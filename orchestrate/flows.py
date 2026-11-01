"""The scheduled run, as Prefect flows that only call Taskfile tasks (ADR-0020).

`run` lists the sources, starts one `ingest-source` flow run per source (its own process or
pod on the work pool, ADR-0021), waits for all of them, then starts one `build` flow run if
any source landed something, and ends Failed when anything did not land (ADR-0022).
`orchestrate/prefect.yaml` declares the deployments, the schedule and the concurrency limits.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import subprocess
import time
from dataclasses import dataclass

from prefect import flow, get_client, get_run_logger
from prefect.client.schemas.objects import FlowRun
from prefect.deployments import run_deployment
from prefect.states import Cancelling, Completed, Failed, State

LIST_COMMAND = ["uv", "run", "task", "ingest:list"]
# `-x` passes the command's own exit status through; without it go-task reports every
# failure as 201, and a partial landing (1) could not be told from none (2).
INGEST_COMMAND = ["uv", "run", "task", "-x", "ingest:source", "--"]
BUILD_COMMAND = ["uv", "run", "task", "-x", "build"]
LIST_TIMEOUT_SECONDS = 5 * 60
INGEST_TIMEOUT_SECONDS = 20 * 60
BUILD_TIMEOUT_SECONDS = 30 * 60
# How long `run` waits for a child to start, and beyond its own timeout, once started, for it
# to end. A child that never starts (no free worker, a pool limit `run` itself fills) would
# otherwise hold `run`, and with it the deployment's only concurrency slot, for good. A build
# may queue behind one other build, so it gets that build's timeout on top.
START_WITHIN_SECONDS = 10 * 60
FINISH_GRACE_SECONDS = 2 * 60
# How long a cancelled child gets to stop (the worker's SIGTERM, then kill after 30 seconds),
# so the build does not start while a cancelled ingest still writes.
STOP_WITHIN_SECONDS = 2 * 60
POLL_SECONDS = 5

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
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        kill_group(proc.pid)
        stdout, stderr = proc.communicate()
        return Outcome(None, stdout, stderr)
    except BaseException:
        kill_group(proc.pid)
        proc.wait()
        raise
    return Outcome(proc.returncode, stdout, stderr)


def kill_group(pid: int) -> None:
    # The group is gone when the command ended just before the interruption.
    with contextlib.suppress(ProcessLookupError):
        os.killpg(pid, signal.SIGKILL)


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
        return Failed(
            name=PARTLY_LANDED, message=f"{source} landed some resources (exit 1)"
        )
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


async def run_child(
    deployment: str,
    parameters: dict,
    timeout_seconds: float,
    start_within_seconds: float,
) -> FlowRun:
    """Start a flow run of ``deployment`` under the current flow and wait for it to end.

    One not started within ``start_within_seconds``, or not ended FINISH_GRACE_SECONDS past
    its own timeout once started, is asked to cancel, which stops its process, and returned
    once cancelled, or after STOP_WITHIN_SECONDS as it then stands; either way the caller
    counts it as failed.
    """
    child = await run_deployment(
        deployment,
        parameters={**parameters, "timeout_seconds": timeout_seconds},
        timeout=0,
        as_subflow=True,
    )
    deadline = time.monotonic() + start_within_seconds
    started = False
    async with get_client() as client:
        while True:
            child = await client.read_flow_run(child.id)
            if child.state.is_final():
                return child
            if not started and child.start_time is not None:
                started = True
                deadline = time.monotonic() + timeout_seconds + FINISH_GRACE_SECONDS
            if time.monotonic() > deadline:
                get_run_logger().warning(
                    f"{deployment} run {child.name} did not finish within its timeout: cancelling"
                )
                # Not forced: a forced Cancelled frees the run's concurrency slot but leaves
                # its process running, and could overwrite a run that has just completed.
                await client.set_flow_run_state(
                    child.id, Cancelling(message="did not finish within its timeout")
                )
                stop_by = time.monotonic() + STOP_WITHIN_SECONDS
                while True:
                    child = await client.read_flow_run(child.id)
                    if child.state.is_final() or time.monotonic() > stop_by:
                        return child
                    await asyncio.sleep(POLL_SECONDS)
            await asyncio.sleep(POLL_SECONDS)


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
    # In a thread, so the event loop keeps renewing `run`'s concurrency lease. A cancellation's
    # signal lands in the main thread and does not kill the listing; its timeout bounds it.
    listing = await asyncio.to_thread(run_command, list_command, LIST_TIMEOUT_SECONDS)
    if listing.exit is None:
        return Failed(
            message=f"listing the sources timed out after {LIST_TIMEOUT_SECONDS}s"
        )
    if listing.exit != 0:
        return Failed(
            message=f"listing the sources failed (exit {listing.exit}): {listing.stderr.strip()}"
        )
    sources = list(
        dict.fromkeys(
            line.strip() for line in listing.stdout.splitlines() if line.strip()
        )
    )
    if not sources:
        return Failed(message="no sources listed: nothing to ingest")

    children = await asyncio.gather(
        *(
            run_child(
                "ingest-source/ingest-source",
                {"source": source, "command": ingest_command},
                ingest_timeout_seconds,
                START_WITHIN_SECONDS,
            )
            for source in sources
        )
    )
    failed = [
        source
        for source, child in zip(sources, children)
        if not child.state.is_completed()
    ]
    problems = [f"sources not fully landed: {', '.join(failed)}"] if failed else []

    if not any(landed(child) for child in children):
        return Failed(message="; ".join(problems) + "; no source landed, so no build")

    built = await run_child(
        "build/build",
        {"target": target, "command": build_command},
        build_timeout_seconds,
        START_WITHIN_SECONDS + build_timeout_seconds,
    )
    if not built.state.is_completed():
        problems.append(
            f"build {built.state.name}: {built.state.message or 'see its log'}"
        )
    if problems:
        return Failed(message="; ".join(problems))
    return Completed(message=f"{len(sources)} sources landed, {target} built")
