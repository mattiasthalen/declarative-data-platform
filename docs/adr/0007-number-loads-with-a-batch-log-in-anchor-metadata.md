# ADR-0007 — Number loads with a batch log and stamp the batch in Anchor's Metadata columns

**Status:** Accepted (2026-10-31)

## Context

The third timeline is when a row was loaded. Every Anchor table has an integer `Metadata_<mnemonic>` column. Lars Rönnbäck's Snowflake skill (`references/metadata.md`) uses it as a key into a batch log.

## Decision

A load log in `integrate` follows that pattern: batch id, started, completed, status (`RUNNING`, `SUCCEEDED`, `VIOLATIONS`) and the count of integrity violations. A `dbt build` that writes Anchor rows opens one batch; every row it writes, anchor rows included, carries that batch id in `Metadata_…`.

Rejected: the dbt invocation id in Metadata, which is a uuid and cannot be ordered.

## Consequences

A bad batch rolls back by deleting its Metadata value from every table. A failed build leaves its batch `RUNNING`; the next build opens a new one.
