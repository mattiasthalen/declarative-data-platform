# ADR-0022 — Build when any source landed, and fail the scheduled run when any source failed

**Status:** Accepted (2026-11-01)

## Context

Ingest exits 0 when every resource of a source landed, 1 when some did, 2 when none did (ADR-0018). A scheduled run has to decide whether to build on a partial lake, and how a failure stays visible when the build is green.

## Decision

The build runs when at least one source exited 0 or 1. The scheduled run then ends Failed if any source did not exit 0, naming those sources, and Failed when no source landed, the listing failed or listed nothing, or the build failed. A crash, a timeout or any other exit status counts as nothing landed.

Rejected: building only when every source landed (one broken source would stop the warehouse for all); ending Completed whenever the build is green (a source failing every hour would never show).

## Consequences

The warehouse stays current for every source that landed. A red run does not mean the warehouse is stale; the operator reads which source failed from the run's message.
