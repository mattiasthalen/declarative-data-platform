# ADR-0030 — Expose the point-in-time perspective as a DuckDB table macro

**Status:** Accepted (2026-11-01)

## Context

Anchor's point-in-time perspective, `p<anchor>` (`pPR_Product`), is a function that takes a changing time and returns one row per identity with each attribute's value in effect then. In Roenbaeck's crt generators it is `t<anchor>(positor, changingTimepoint, EOT, '+')` for every positor (`SQL/Snowflake/crt/CreateAnchorPerspectives.sisula`). Integrate is generated dbt on DuckDB (ADR-0006), and the integrate generator already writes the latest perspective `lPR_Product` as a view. DuckDB has no `CREATE FUNCTION ... RETURNS TABLE`; it has table macros (`CREATE MACRO name(param) AS TABLE select ...`), stored in the database file and expanded where they are called. dbt materializes models as tables, views and incremental tables, not as macros.

## Decision

The integrate generator writes `p<anchor>` for every anchor beside `l<anchor>`, as a DuckDB table macro in the `integrate` schema taking one parameter, `changingTimepoint`, and returning `l<anchor>`'s columns: per identity, each attribute's latest reliable posit as positor 0 states it, among those with a ChangedAt at or before `changingTimepoint`. It is called as `select * from integrate."pPR_Product"(date '2013-06-01')`. A materialization in `macros/integrate/` creates it with `create or replace macro` on every build.

Rejected: a view of every version with its own valid-from and valid-to, filtered by the caller, because it is not Roenbaeck's shape or name and repeats what serve's dimension already gives.

## Consequences

Integrate offers the crt reads that matter for one positor: the assembled views (every statement), `l<anchor>` (latest) and `p<anchor>` (any changing time); Roenbaeck's now perspective `n<anchor>` is `p<anchor>` at the current time and is not generated. A downstream model can use the macro only as a call, `{{ ref('pPR_Product') }}(<time>)`, and no generic dbt test can select from it; it is checked by the test suite. It is designed and tested to be called once per time, not for each row of another table. The time is compared with ChangedAt as the source's own clock, which carries no zone (A6): a date means its midnight, and a `timestamptz` such as `now()` is read in the session's time zone. A dbt materialization of our own is code to keep working across dbt-duckdb upgrades (A24). The as-known-at perspective (positing time, #5) is a separate decision.
