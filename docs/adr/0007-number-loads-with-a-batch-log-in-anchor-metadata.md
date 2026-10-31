# ADR-0007 — Number loads with a batch log and stamp the batch in Anchor's Metadata columns

**Status:** Accepted (2026-10-31)

## Context

The third timeline is when a row was loaded. Anchors and annexes have an integer `Metadata_<mnemonic>` column; in crt a posit has none, since the same posit can be asserted and retracted by different batches. Lars Rönnbäck's Snowflake skill (`references/metadata.md`) uses it as a key into a batch log.

## Decision

A load log in `integrate` follows that pattern: batch id, started, completed, status (`RUNNING`, `SUCCEEDED`, `VIOLATIONS`) and the count of integrity violations. A `dbt build` that writes Anchor rows opens one batch; every anchor and annex row it writes carries that batch id in `Metadata_…`.

Rejected: the dbt invocation id in Metadata, which is a uuid and cannot be ordered.

## Consequences

A bad batch rolls back by deleting its annex and anchor rows, then every posit left without an annex row. A batch stays `RUNNING` until serve has read it: a build where a node errored or was skipped, or that did not build every serve model, leaves it `RUNNING`, and serve rebuilds the identities of every `RUNNING` batch. The next build that builds all of serve closes every `RUNNING` batch, `SUCCEEDED` or `VIOLATIONS` by the integrity violations at that time. A failed test holds a batch open only when it skips a serve model, as a failing test on a staged bridge does; a failing `IntegrityViolations` test skips nothing in serve, and `VIOLATIONS` records it. A build that wrote no Anchor row leaves no batch of its own.
