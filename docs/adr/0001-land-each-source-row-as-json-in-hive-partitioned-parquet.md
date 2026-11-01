# ADR-0001 — Land each source row as JSON in hive-partitioned Parquet, one dlt pipeline per resource

**Status:** Accepted (2026-10-31)

## Context

The lake is the contract between ingestion and everything after it. Contracts in conform read source fields by path and own every cast (Daana, "Contract-driven data transformation"). A resource that fails must not stop the other resources of its source.

## Decision

dlt writes Parquet under `LAKE_ROOT` (default `./lake`), hive style `date=YYYY-MM-DD/hour=HH`, with the source row as one JSON field next to dlt's own meta fields (`_dlt_load_id`, `_dlt_id`). Nothing is renamed or typed at landing. Each resource runs as its own dlt pipeline, named `<source>__<resource>` (`adventure_works__products`); `uv run ingest` runs them all, carries on past a failure and exits non-zero if any failed.

Rejected: flattened, typed columns at landing, which moves casting and naming out of the contract and makes a source schema change break ingestion; one pipeline per source, where one faulty resource halts the rest.

## Consequences

Conform reads JSON paths, so a renamed source field is a contract change, not a lake migration. The lake grows by a full copy per run for full-pull resources. Making ingest itself declarative is a separate backlog item.

dlt writes under `<bucket>/<dataset>/<layout>` and keeps its own bookkeeping in the dataset folder. The dataset is `_dlt`, so that bookkeeping sits in `$LAKE_ROOT/_dlt/`, and the layout starts with `../{table_name}/` so each resource sits directly under `LAKE_ROOT`. That step out of the dataset folder relies on the filesystem destination resolving `..` in a local path; a remote bucket needs another layout.

A load lands file by file. A build that reads the lake while ingest is still writing a load can stage part of it, and conform's watermark then skips the rest (A4).

An OData next link, resolved against the page it came from, is followed only to the feed's own scheme, host and port, and no request follows a redirect; either fails the resource.

## Addendum 2026-10-31

The resources are now declared, not written in Python: ADR-0016 (dlt's own configuration in YAML), ADR-0017 (`sources/<source>/`, one file per resource), ADR-0018 (per-source runs and exit codes 0, 1, 2). The next-link origin guard and the refusal of redirects are applied in code to every declared resource. Every load is appended.
