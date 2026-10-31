# ADR-0010 — Cast with try_cast, and never let a failed cast retract

**Status:** Accepted (2026-10-31)

## Context

A producer's bad value must not stop the load (the prior art's rule). In crt a null value is a retraction (ADR-0006), so a cast that fails to null would retract what Anchor holds.

## Decision

Conform casts with `try_cast`. A dbt warn test names each property and contract whose non-null source value failed. The staged model carries `_contract__cast_failed`, the list of those properties per row, and the Anchor load skips those attributes for that row. Only a null in the source retracts. A contract may rewrite its own value before the cast (`transformLogic`, such as `trim(value)`), and nothing else.

Rejected: strict casts, which stop every layer on one bad value; failing only on required properties; letting a failed cast retract, which loses a held value to a producer's typo.

## Consequences

A bad value is visible as a warning and changes nothing in Anchor; the next good load posits normally.
