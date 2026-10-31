---
paths:
  - "**/integrate/**"
  - "/anchor/**"
---

# Integrate rules

Anchor Modeling's own reference is `docs/ANCHOR.md` in
[Roenbaeck/anchor](https://github.com/Roenbaeck/anchor); read it before changing the load. Clone
it read-only: `GIT_LFS_SKIP_SMUDGE=1 git clone --depth 1 https://github.com/Roenbaeck/anchor`.

- **Keep Roenbaeck's default naming verbatim**: `PR_Product`, `PR_NAM_Product_Name_Posit`,
  `lPR_Product` ([ADR-0003](../../docs/adr/0003-keep-anchor-modeling-default-naming-verbatim.md)).
- **No static attributes.** Every attribute in `anchor/model.yaml` has a `timeRange`.
- **`anchor/model.yaml` is the whole model and uses only `anchor.xsd`'s elements and attributes.**
  Where an anchor's attributes come from goes in `anchor/mappings/<anchor>.yaml`, one per anchor
  ([ADR-0004](../../docs/adr/0004-declare-the-anchor-model-as-one-yaml-mirror-of-anchor-xsd.md)).
- **The crt loading rules live in the generated SQL** (`macros/integrate/anchor.sql`): decisive,
  idempotent, not assertive, since DuckDB has no triggers
  ([ADR-0006](../../docs/adr/0006-apply-anchor-crt-loading-rules-in-generated-sql.md)).
