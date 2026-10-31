---
paths:
  - "**/conform/**"
  - "/contracts/**"
  - "/models/raw/**"
---

# Conform rules

- **One ODCS v3 contract per source object** in `contracts/`. The generator turns it into the
  `raw` view over the lake and the staged model in `conform`.
- **Columns keep the source's words in snake_case** (`ProductLine` becomes `product_line`).
  The columns describing the extraction start `_dlt__`
  ([ADR-0002](../../docs/adr/0002-name-conformed-columns-in-snake-case-with-dlt-platform-columns.md));
  the contract's own flag is `_contract__cast_failed` (below).
- **Cast with `try_cast`, and a failed cast never retracts.** It is flagged in
  `_contract__cast_failed`, warned about, and skipped by the Anchor load; only a null in the
  source retracts. A contract may rewrite its value before the cast in `transformLogic`
  ([ADR-0010](../../docs/adr/0010-cast-with-try-cast-and-never-let-a-failed-cast-retract.md)).
- **Append every newer load whole; never deduplicate.** Integrate drops what it already knows
  ([ADR-0009](../../docs/adr/0009-stage-conform-by-appending-whole-loads.md)).
