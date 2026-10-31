# ADR-0008 — Track the Anchor model in the database with Anchor's schema tables

**Status:** Accepted (2026-10-31)

## Context

The query skill will reach the database but not the repository, and must know what each anchor and attribute means. Roenbaeck's PostgreSQL target keeps the model in the database (`CreateSchemaTracking.js`).

## Decision

Integrate ports that tracking: `_Schema` (version, activation, the model as JSON; a new row only when the model changes), `_Schema_Expanded`, `_Anchor`, `_Attribute`, `_Knot` and `_Tie`. Every anchor and attribute carries a description in `model.yaml`.

Rejected: also putting contracts and mappings in the database now, before the query skill says what it needs.

## Consequences

The model's history lives in the database as well as in git. Contract and serve metadata are a later decision.
