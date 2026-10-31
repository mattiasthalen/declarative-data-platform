# ADR-0009 — Stage conform by appending every newer load whole, and let Anchor discard repeats

**Status:** Accepted (2026-10-31)

## Context

Most sources are pulled in full, which suits non-transactional data; some will be pulled incrementally. Staged versions by digest and stamp are story 4.

## Decision

Per contract, `raw` holds a view over the lake (`read_parquet` with `filename` and `hive_partitioning`), and the staged model in `conform` is incremental and appends every load whose `_dlt__load_id` is newer than its newest. Conform does not deduplicate; Anchor's loading rules (ADR-0006) drop what is already known.

Rejected: staging only changed rows, which brings story 4's digest forward.

## Consequences

The same rule serves full and incremental extracts. The staged model grows by a full copy per full load until story 4.
