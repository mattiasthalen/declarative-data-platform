---
paths:
  - "/src/serve/**"
  - "/macros/serve/**"
  - "/models/serve/uss*/**"
---

# Unified Star Schema rules

The USS is everything in serve but its hand-written models: the generator `src/serve/`, its
models in `models/serve/uss_staging/` and `models/serve/uss/`, and `macros/serve/` ([ADR-0011](../../docs/adr/0011-serve-a-uss-from-staged-bridges-unioned-by-name.md)).

- **One staged bridge per entity**, and a relationship adds exactly one step: an order line gets
  its customer through the order's bridge, never directly. The bridge is the union by name of
  the staged bridges ([ADR-0011](../../docs/adr/0011-serve-a-uss-from-staged-bridges-unioned-by-name.md)).
- **Two ghost rows per dimension**: *not available* for a null inside a staged bridge, *not
  applicable* for a key the union leaves null ([ADR-0011](../../docs/adr/0011-serve-a-uss-from-staged-bridges-unioned-by-name.md),
  [lexicon](../../docs/lexicon.md)).
