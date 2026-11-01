# ADR-0021 — Ingest each source in its own flow run, then build once

**Status:** Accepted (2026-11-01)

## Context

Ingest runs per source and reports 0, 1 or 2 (ADR-0018). The warehouse is one DuckDB file per target, and DuckDB's file lock admits one writer (A4). A scheduled run must keep sources apart and keep the build single.

## Decision

A scheduled run starts one ingest flow run per source, all at once, each on its own pod on the work pool (its own process on a local one). Once every one of them has finished, one build flow run builds the target. The build never fans out.

Rejected: one build per source (concurrent writers to one DuckDB file); running every source in the scheduled run's own process (a source that hangs or crashes takes the others with it, and the pod per source shape is lost).

## Consequences

A slow source delays the build until it finishes or times out (20 minutes). Once pods run on separate machines they need the lake and the DuckDB file on shared storage; that comes with multi-environment deploys.
