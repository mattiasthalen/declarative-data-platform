# ADR-0036 — Load a to-one tie as an attribute of its identifier role

**Status:** Accepted (2026-11-03)

## Context

The model gains its first tie, `PR_in_PS_contains`: a historized many-to-one tie from Product (`in`, the identifier role) to ProductSubcategory (`contains`). Roenbaeck's crt stores a tie as a posit table keyed by its roles and ChangedAt and an annex table, as an attribute is stored. ADR-0006 fixes the load rules for attributes: decisive, idempotent, not assertive, with restatements skipped and a source null retracting; the generated load also fails the build when one load gives one version two values. Ties to come (#27's Transaction to Product) take the same shape.

## Decision

A tie whose only identifier role is one anchor's is loaded by that anchor's mapping, under the attribute rules of ADR-0006 and ADR-0010, with the identity in the other role as its value: per identifier identity and ChangedAt, the same value is idempotent, the same value as the version before is a restatement and skipped, another value at a held ChangedAt is a correction, and a source null retracts the version in effect. One load macro serves attributes and ties. Two values for one identity and ChangedAt in one load are a contradiction, and the build fails.

Rejected: keeping both values and only warning, as crt's tie tables allow (their unique key includes the value role). Serve would then count the product under both subcategories, or pick one silently. A relationship that can hold several values at once is a many-to-many tie, declared as one (#7). Rejected: a separate tie load, which would hold a second copy of the crt rules.

## Consequences

The tie's history behaves as an attribute's: corrections, retractions and late arrivals read the same way in `l`, `p(T)` and `t(T, K)`. A source that legitimately relates one product to several subcategories fails the build until the tie is declared many-to-many. The tie's key check (`ic_<tie>`) still runs, at `severity: warn`, for what the load cannot prevent, such as a posit written twice (A5).
