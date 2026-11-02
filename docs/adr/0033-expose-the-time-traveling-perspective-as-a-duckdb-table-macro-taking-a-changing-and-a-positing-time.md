# ADR-0033 — Expose the time-traveling perspective as a DuckDB table macro taking a changing and a positing time

**Status:** Accepted (2026-11-02)

## Context

An analyst asks what was believed true at a changing time T, as known at a positing time K, so that a late correction does not silently rewrite the past. Integrate already stores what that needs: PositedAt is each load's extraction time (ADR-0006), and a correction keeps the earlier posit, retracting it in the annex at the new PositedAt. Its reads do not use it: `l<anchor>` and the point-in-time table macro `p<anchor>(changingTimepoint)` (ADR-0030) read every annex row there is. In Roenbaeck's crt generators the perspective that takes both times is the time-traveling one, `t<anchor>(positor, changingTimepoint, positingTimepoint, assertion)` (`SQL/Snowflake/crt/CreateAnchorPerspectives.sisula`), built on the attribute rewinders, which keep posits with a ChangedAt at or before the changing time and annex rows with a PositedAt at or before the positing time; `l` and `p` are calls of it. Integrate has one positor and asserts only positively (ADR-0006).

## Decision

The integrate generator writes `t<anchor>` for every anchor beside `l<anchor>` and `p<anchor>`, as a DuckDB table macro in the `integrate` schema taking `changingTimepoint` and `positingTimepoint`, created by the `table_macro` materialization of ADR-0030. It returns `l<anchor>`'s columns: per identity, each attribute's version in effect at `changingTimepoint` as positor 0 had stated it by `positingTimepoint`, by crt's rules. It is called as `select * from integrate."tPR_Product"(date '2014-01-01', timestamp '2026-11-01 10:00')`. `p<anchor>` stays as ADR-0030 decided, and the three perspectives are generated from one select.

Rejected: an optional positing parameter on `p<anchor>`, because crt's `p` takes the changing time alone and it would supersede part of ADR-0030; crt's full four parameters, because positor and assertion each take one value while integrate has one positor and positive assertions only.

## Consequences

"As known at" is answered from integrate; serve stays on changed-at alone and never reads positing time. `t<anchor>` at a positing time at or after the latest load equals `p<anchor>` at the same changing time. Like `p<anchor>`, it is designed to be called once per pair of times, not for each row of another table, and no generic dbt test can select from it. The positing time is compared with PositedAt, a zone-less timestamp in UTC: a date means its midnight in UTC, and a `timestamptz` such as `now()` is read in the session's time zone (A28). A second positor, or negative assertions, would add crt's other two parameters, and that change would supersede this decision.
