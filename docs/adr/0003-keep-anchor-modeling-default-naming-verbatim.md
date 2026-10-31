# ADR-0003 — Keep Anchor Modeling's default naming verbatim in integrate

**Status:** Accepted (2026-10-31)

## Context

The integrate layer must be true to Roenbaeck/anchor, so its docs, its modeler and Lars Rönnbäck's skills read our tables without translation. Its naming joins mnemonics and PascalCase descriptors with a hard-coded `_` (`var D = '_'` in `SQL/NamingConvention.js`); the suffixes (`ChangedAt`, `Posit`, `Annex`, `PositedAt`, `Positor`, `Reliability`, `Metadata`) are model settings. The rest of the platform is snake_case with `__` (ADR-0002).

## Decision

Integrate uses Anchor's default naming as it is: `PR_Product`, `PR_NAM_Product_Name_Posit`, `PR_NAM_ChangedAt`, `Metadata_PR_NAM`, `lPR_Product`, `key_PR_Product_NUM`. Mnemonics are two letters for anchors and three for attributes, descriptors PascalCase.

Rejected: lowercase descriptors and suffixes through the model's settings, which stays within Anchor's rules but reads unlike every Anchor reference; `__` as the delimiter, which Anchor's code cannot produce.

## Consequences

Integrate is the one layer whose names differ in style from the rest. DuckDB identifiers are case-insensitive, so queries may still be written in lowercase. Renaming later means renaming every Anchor table and view.
