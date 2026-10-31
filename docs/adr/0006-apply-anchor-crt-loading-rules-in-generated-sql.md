# ADR-0006 — Apply Anchor's crt loading rules in generated SQL: decisive, idempotent, not assertive

**Status:** Accepted (2026-10-31)

## Context

Anchor is concurrent-reliance-temporal from the first delivery, with one positor. Its SQL Server and Snowflake targets enforce the loading rules with triggers ("Loading through the latest views", `docs/ANCHOR.md`); DuckDB has none, and Lars's Snowflake skill covers uni-temporal loading only. Full-pull sources state every value again on every run.

## Decision

The integrate generator emits load SQL that applies ANCHOR.md's rules table itself, with the model set to decisive, idempotent and not assertive:

- identical: nothing; a restatement (same value, later ChangedAt): skipped;
- a new value: a posit and an annex at reliability 1;
- another value at a held ChangedAt: a correction, a retraction at reliability 0 and the new assertion at the new PositedAt; a correction back to the previous version's value is a skipped restatement that still retracts;
- a null from the source: a retraction; a key missing from a load: nothing;
- loads apply in positing order, oldest load id first; two assertions of one version by one positor at one PositedAt fail the build.

PositedAt is `_dlt__extracted_at`, ChangedAt the source's change time, positor 0.

Rejected: assertive, under which every full load writes a re-assertion of every value; retracting keys missing from a full load, which needs the contract to declare the source a full snapshot and is left to a later story.

## Consequences

The generated load is the only enforcement, so `IntegrityViolations` and the `ic_` views are tested after every build. Assertions that arrive out of positing order are not reordered, as in Anchor's triggers.
