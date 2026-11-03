# ADR-0039 — Backfill a tie's first version in serve as an attribute's

**Status:** Accepted (2026-11-03)

## Context

ADR-0011 takes each attribute's first value to have held since `0001-01-01` in serve. Every product row's ModifiedDate on the feed is 2014-02-08, while sell starts reach back to 2008, so a tie that starts at its first ChangedAt leaves every product without a subcategory before 2014-02-08.

## Decision

In serve, a tie's first version per identifier identity holds from `0001-01-01`, as an attribute's first value does. Integrate does not backfill (ADR-0011, addendum 2026-11-01).

Rejected: starting a tie at its first ChangedAt, under which "products on sale per subcategory" shows every product as `[not available]` for six years.

## Consequences

A question before a product's first ChangedAt reads its earliest subcategory. Serve and integrate agree from the tie's first ChangedAt on.
