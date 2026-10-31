# ADR-0001 — Land each source row as JSON in hive-partitioned Parquet, one dlt pipeline per resource

**Status:** Accepted (2026-10-31)

## Context

The lake is the contract between ingestion and everything after it. Contracts in conform read source fields by path and own every cast (Daana, "Contract-driven data transformation"). A resource that fails must not stop the other resources of its source.

## Decision

dlt writes Parquet under `LAKE_ROOT` (default `./lake`), hive style `date=YYYY-MM-DD/hour=HH`, with the source row as one JSON field next to dlt's own meta fields (`_dlt_load_id`, `_dlt_id`). Nothing is renamed or typed at landing. Each resource runs as its own dlt pipeline, named `<source>__<resource>` (`adventure_works__products`); `uv run ingest` runs them all, carries on past a failure and exits non-zero if any failed.

Rejected: flattened, typed columns at landing, which moves casting and naming out of the contract and makes a source schema change break ingestion; one pipeline per source, where one faulty resource halts the rest.

## Consequences

Conform reads JSON paths, so a renamed source field is a contract change, not a lake migration. The lake grows by a full copy per run for full-pull resources. Making ingest itself declarative is a separate backlog item.
