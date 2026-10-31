---
paths:
  - "**/uss*"
  - "**/uss*/**"
---

# Unified Star Schema rules

The USS is serve's generated part: `models/serve/uss_staging/`, `models/serve/uss/` and
`macros/serve/uss.sql` ([ADR-0011](../../docs/adr/0011-serve-a-uss-from-staged-bridges-unioned-by-name.md)).

- **One staged bridge per entity**, and a relationship adds exactly one step: an order line gets
  its customer through the order's bridge, never directly. The bridge is the union by name of
  the staged bridges.
- **Two ghost rows per dimension**: *not available* for a null inside a staged bridge, *not
  applicable* for a key the union leaves null ([lexicon](../../docs/lexicon.md)).
