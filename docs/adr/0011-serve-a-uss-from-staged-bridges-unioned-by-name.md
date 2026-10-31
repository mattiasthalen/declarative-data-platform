# ADR-0011 — Serve a Unified Star Schema from incremental staged bridges unioned by name

**Status:** Accepted (2026-10-31)

## Context

Serve is a Puppini Unified Star Schema on business time. Relationships must inherit keys one step at a time, and two kinds of missing must stay distinguishable.

## Decision

Each entity gets an incremental staged bridge in `serve__uss_staging` (`bridge__product`) holding its own PIT keys; a relationship adds exactly one step (order line gets customer through order's bridge). `serve__uss._bridge` is a `union all by name` of the staged bridges, with `stage`, `_key__<entity>`, `_valid_from` and `_valid_to`. Each dimension (`serve__uss.product`) has one row per version, a PIT key of identity and valid-from, an opening version from `0001-01-01`, and two ghost rows: `[not available]` for a null inside a staged bridge, `[not applicable]` for a null the union creates. Serve uses changed-at only.

Rejected: tables rebuilt on every build, and views, which redo the overlap joins every query.

## Consequences

Adding an entity adds a staged bridge without touching the others. "As known at" questions are answered in integrate, not serve.
