# ADR-0020 — Expose the platform to orchestrators as Taskfile tasks, one per unit of work

**Status:** Accepted (2026-11-01)

## Context

The platform must run on a schedule without anyone at the keyboard, and which orchestrator runs it may change: Prefect is the first, Kestra was the ticket's first candidate, and the infra that runs it belongs to another repo. Whatever schedules the work must be able to fan ingest out and run the build alone.

## Decision

Orchestrators call Taskfile tasks and nothing else. Each task is one unit an orchestrator can place on its own pod: list the sources (`task ingest:list`), ingest one source (`task -x ingest:source -- SOURCE`), build one target (`task -x build TARGET=…`). `-x` is part of the interface: without it go-task reports any failing command as exit 201, which hides ingest's 1 and 2 (ADR-0018). The order of the units, the fan-out and the schedule live in the orchestrator's flow, not in the Taskfile.

Rejected: one Taskfile task running the whole flow (an orchestrator could only run it as a single pod, with no fan-out); flows that call `uv run ingest` and `dbt` directly (every orchestrator would repeat how each layer is run, and a change to that would touch every flow).

## Consequences

Switching orchestrator means rewriting only `orchestrate/`. A task an orchestrator calls is an interface: renaming it, or changing what its exit status means, breaks every flow that calls it.
