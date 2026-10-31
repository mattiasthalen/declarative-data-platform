# ADR-0002 — Name conformed columns in snake_case, and group platform columns under `_dlt__`

**Status:** Accepted (2026-10-31)

## Context

Conform is where source names become the platform's names; every later layer reads them. Some columns describe the data, others the extraction. Readers must tell the two apart, and platform columns must never collide with a source field.

## Decision

Contract properties are snake_case and keep the source's words (`ProductLine` → `product_line`). A double underscore separates concerns. Every column the platform adds carries `_dlt__`: `_dlt__load_id`, `_dlt__id`, `_dlt__extracted_at` (the load id, fractional epoch seconds as text, cast to a timestamp to the microsecond), `_dlt__extracted_on` and `_dlt__extracted_hour` (the hive folders), `_dlt__file_name`. Schemas follow the same rule: `serve__uss`, `serve__uss_staging`.

Rejected: an owner prefix on every column (`product__line`), which renames the source's words; `__` only for nested paths, which leaves platform columns ungrouped; a `_lake__` prefix, since dlt is the canonical owner; extracted-at from the hour folder, which truncates it to the hour.

## Consequences

Every contract and generator spells platform columns the same way. `_dlt__extracted_at` keeps microseconds, so two loads share it only if they start in the same microsecond; the load handles that case anyway (ADR-0006). The Anchor layer does not follow this rule: it keeps Anchor's own naming (ADR-0003).
