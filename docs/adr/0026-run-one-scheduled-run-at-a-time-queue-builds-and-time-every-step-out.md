# ADR-0026 — Run one scheduled run at a time, queue builds, and time every step out

**Status:** Accepted (2026-11-01)

## Context

DuckDB admits one writer per file (A4), and the schedule fires every hour whether or not the last run has finished. Prefect can hold a deployment to a number of concurrent runs and, when the limit is reached, either cancel the newcomer or queue it.

## Decision

`run` is limited to one at a time and cancels a newcomer (cancel-new); `build` is limited to one at a time and queues a newcomer (enqueue). The listing times out after 5 minutes, each source's ingest after 20, the build after 30; `run` gives each child 10 minutes to start (a build 40, since it may queue behind one other build) and, once started, 2 minutes beyond its timeout to end; past either it asks the child to cancel, which stops its process, and counts it failed. A timeout counts as that step failing (ADR-0022).

Rejected, for `run`: enqueue (runs pile up behind a slow one, and the next run covers the same ground anyway). For `build`: no limit (a second build fails on the DuckDB lock) and cancel-new (a build started by hand would vanish silently). For the steps: no timeout (one hung step, or a child that never starts, holds `run`'s only slot and every later hourly run is cancelled, silently).

## Consequences

A scheduled run lasts at most about two hours before it ends Failed and frees the slot, and that only when its build cannot start for 40 minutes; with free workers and no build ahead of it, about an hour and a quarter. A build started by hand in Prefect queues behind the scheduled build, and the scheduled build behind it, but neither is held off the other's ingest; nothing started with `task` is held off at all (A4).
