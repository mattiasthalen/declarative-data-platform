# ADR-0006 — Apply Anchor's crt loading rules in generated SQL: decisive, idempotent, not assertive

**Status:** Accepted (2026-10-31)

## Context

Anchor is concurrent-reliance-temporal from the first delivery, with one positor. Its SQL Server and Snowflake targets enforce the loading rules with triggers ("Loading through the latest views", `docs/ANCHOR.md`); DuckDB has none, and Lars's Snowflake skill covers uni-temporal loading only. Full-pull sources state every value again on every run.

## Decision

The integrate generator emits load SQL that applies ANCHOR.md's rules table itself, with the model set to decisive, idempotent and not assertive:

- identical: nothing; a restatement (same value, later ChangedAt): skipped;
- a new value: a posit and an annex at reliability 1;
- another value at a held ChangedAt: a correction, a retraction at reliability 0 and the new assertion at the new PositedAt; a correction back to the previous version's value is a skipped restatement that still retracts;
- a null from the source: a retraction of the version in effect at its ChangedAt; a key missing from a load: nothing;
- a row that repeats the key's row in the load before is not applied again, so unchanged full pulls add no steps to the load, though each build still reads the whole conform history once per attribute; only a key's lone row in a load is compared, so two rows that contradict each other in one load always reach the check below;
- loads apply in positing order, oldest load id first, and within a load in ChangedAt order; two assertions of one version by one positor at one PositedAt fail the build.

PositedAt is `_dlt__extracted_at`, ChangedAt the source's change time, positor 0.

Rejected: assertive, under which every full load writes a re-assertion of every value; retracting keys missing from a full load, which needs the contract to declare the source a full snapshot and is left to a later story.

## Consequences

The generated load is the only enforcement, so `IntegrityViolations` and the `ic_` views are tested after every build. Assertions that arrive out of positing order are not reordered, as in Anchor's triggers.

crt has no way to assert that an attribute has no value, so a null retracts what is held. When a product has more than one version and the source nulls the attribute, the version in effect is retracted and the one before it is in effect again: the latest view shows the older value, not null.

Integrate is only ever appended to. A full refresh would renumber identities against the tables it replaces, so the integrate models set `full_refresh: false`: dbt ignores `--full-refresh` for them and builds incrementally.

The `ic_` views check duplicate keys and more than one reliable assertion at one time. Roenbaeck's crt checks for temporal duplicates and restatements are not generated yet; the load skips restatements, so those checks would guard the load rather than the data.
