# ADR-0027 — Simulate source change by appending seeded, changed copies of the latest load

**Status:** Accepted (2026-11-01)

## Context

The AdventureWorks feed is static: every Product's `ModifiedDate` is 2014-02-08 and nothing ever changes, so neither CI nor a person running the platform can watch history accumulate. CI needs the same history on every run; a person needs to change their own lake. The history stories (#4 onward) need both. The lake is append-only and every load is a full Products extract (ADR-0001, ADR-0009).

## Decision

One seeded simulator, `uv run simulate [--seed N] [--loads K]`, appends Product loads to `$LAKE_ROOT` in dlt's landed shape, each a copy of the previous load with about 5% of products changed by a fixed mix: edits (50%), corrections (15%), source nulls (10%), late arrivals (10%), new products (5%) and products dropping out of one load (10%). Every load changes at least six products, one of each kind, except that a product drops out for one load only: a run's last load drops none, since no later load of the run would bring it back, and a product just back is not dropped again; those drop outs are edits instead. Only the six attributes the business question reads change. On an empty lake it first lands a committed snapshot of the real feed, then spaces the changed loads one day apart from a fixed date, so a seed always gives the same rows in the same loads. On a lake that holds Products loads it starts from the latest one and stamps each new load with the current time, as a real ingest would. It never rewrites or removes a load. The seed defaults to a random value and is printed; CI passes a fixed one. `task simulate` wraps it.

Rejected: separate commands for the CI fixture and for the live lake, because they would be two paths over one change engine and drift apart; per-kind rate options, because nobody needs to tune the mix yet and every option is surface to keep; generating the starting products from the seed, because every quirk of the real feed (padded product lines, null colours and sell ends) would have to be hand-coded and kept true, and CI's rows would differ from a live lake's.

## Consequences

CI and every history story replay the same history from a seed. The snapshot is a data file in the repository; it goes stale only if the feed changes, and is refreshed by hand. Simulated rows break A2 on purpose (corrections change a value without moving `ModifiedDate`). A live lake that has been simulated holds invented values beside real ones; there is no undo beyond deleting the simulated loads' files. The simulator writes Parquet directly rather than through a dlt pipeline, so dlt's own state is not touched; Products has no cursor, so nothing depends on it. "The same seed" means on the same Python minor version: the standard library promises stable seeding, not stable `sample` or `shuffle` across versions, and CI pins Python 3.13. Row ids (`_dlt_id`) are derived from the seed and the starting load, so a seed reused on a grown lake repeats none. Other resources are not simulated. The simulator knows Products by name, so it lives in its own package, `src/simulate/`, not in ingest, whose code names no resource (ADR-0016); rejected: a generic simulator in ingest reading contracts and anchor mappings, because ingest would read integrate's declarations.
