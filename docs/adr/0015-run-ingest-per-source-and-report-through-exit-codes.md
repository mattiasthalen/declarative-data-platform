# ADR-0015 — Run ingest per source, and report through exit codes 0, 1 and 2

**Status:** Accepted (2026-10-31)

## Context

The orchestrator (story 16) runs one pod per source and then one `dbt build`, and builds when at least one resource landed. A pod tells the orchestrator only through its exit status. ADR-0001 runs each resource as its own dlt pipeline so one faulty resource does not halt the rest.

## Decision

`uv run ingest` takes nothing (every source), a source name, or `<source>__<resource>` (one resource); `uv run ingest --list` prints one source name per line. Within a run, each resource is its own dlt pipeline and a failure is named on stderr while the rest go on. The exit status is 0 when every resource landed, 1 when some landed and some failed, and 2 when none landed or a name is unknown. A resource has landed when its pipeline completed, even with no new rows.

Rejected: one pod per resource, which multiplies pods and dlt start-up for sources with many small resources and moves the failure isolation dlt already gives us into the orchestrator; a plain non-zero exit for any failure, which cannot tell the orchestrator whether anything is worth building.

## Consequences

The orchestrator decides from exit codes alone and needs no knowledge of resources. A pod that exits 1 still feeds the build, so a resource can stay stale for many runs while its source keeps landing; stderr is where that shows.
