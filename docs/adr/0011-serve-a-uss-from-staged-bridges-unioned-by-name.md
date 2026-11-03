# ADR-0011 — Serve a Unified Star Schema from incremental staged bridges unioned by name

**Status:** Accepted (2026-10-31)

## Context

Serve is a Puppini Unified Star Schema on business time. Relationships must inherit keys one step at a time, and two kinds of missing must stay distinguishable.

## Decision

Each entity gets an incremental staged bridge in `serve__uss_staging` (`bridge__product`) holding its own PIT keys; a relationship adds exactly one step (order line gets customer through order's bridge). `serve__uss._bridge` is a `union all by name` of the staged bridges, with `stage`, `_key__<entity>`, `_valid_from` and `_valid_to`. Each dimension (`serve__uss.product`) has one row per version, a PIT key of identity and valid-from, a first version from `0001-01-01`, and two ghost rows: `[not available]` for a null inside a staged bridge, `[not applicable]` for a null the union creates. Serve uses changed-at only.

Rejected: tables rebuilt on every build, and views, which redo the overlap joins every query.

## Consequences

Adding an entity adds a staged bridge without touching the others.

Each attribute's first value is taken to have held since `0001-01-01`, so the first version starts there and no version is all null. A question about a day before the source's first change time reads the earliest values seen (Mattias at the evidence gate, 2026-10-31). Rejected: an all-null opening version, under which every live product was empty before its only `ModifiedDate`; and starting each product at its first change, under which it is missing before it. "As known at" questions are answered in integrate, not serve.

## Addendum 2026-11-01

The backfill of each first value to `0001-01-01` is serve's alone. Integrate never backfills: the point-in-time perspective `pPR_Product` ([ADR-0030](0030-expose-the-point-in-time-perspective-as-a-duckdb-table-macro.md)) shows no value for an attribute before its first ChangedAt, as Roenbaeck's crt views do: a posit says nothing about the time before it (Mattias, 2026-11-01: "serve backfills, anchor is true"). Serve and integrate therefore agree from each attribute's first ChangedAt on; before it, serve shows the first value and integrate shows none. Rejected: backdating the first posit in integrate, because the perspective would state a value nobody posited.

## Addendum 2026-11-03

Relationships reach the staged bridges as [ADR-0038](0038-split-a-staged-bridge-at-every-change-of-what-it-reaches-over-to-one-ties.md) decides: a staged bridge follows each tie in which its anchor is the only identifier role, one step, and is split at every change of what it reaches. Ties are backfilled as attributes are ([ADR-0039](0039-backfill-a-ties-first-version-in-serve-as-an-attributes.md)).
