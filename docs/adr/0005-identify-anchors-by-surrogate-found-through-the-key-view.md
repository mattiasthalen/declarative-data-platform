# ADR-0005 — Identify anchors by a surrogate found through the key view

**Status:** Accepted (2026-10-31)

## Context

Rows arrive with natural keys (ProductNumber). Every attribute is historized, the natural key included, so a key can change while the thing stays the same.

## Decision

An anchor's identity (`PR_ID`) is a surrogate integer. A natural key the key view (`key_PR_Product_NUM`) does not know gets the next identity; a known key reuses its identity. This is Anchor's `generator` behaviour.

Rejected: a hash of the natural key, which gives the same id in every target without a lookup but splits one thing into two when its key changes.

## Consequences

`dev` and `prod` may number the same product differently; nothing joins across targets. The load needs the key view before it writes, so identities are assigned in one place per build.
