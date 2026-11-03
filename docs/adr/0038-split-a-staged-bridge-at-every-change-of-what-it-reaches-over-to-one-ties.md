# ADR-0038 — Split a staged bridge at every change of what it reaches over to-one ties

**Status:** Accepted (2026-11-03)

## Context

ADR-0011 gives each entity a staged bridge holding its own PIT keys, and inherits a relationship's keys one step at a time. A product's subcategory, and the subcategory's name, change on their own timelines. A bridge row that names one PIT key per dimension must be valid for the whole of its interval, or a question at an instant picks the wrong version or two rows.

## Decision

A staged bridge follows every tie in which its anchor is the only identifier role, one step, to the other anchor's staged bridge, and inherits every key that stage carries. Its rows are its own versions intersected with the tie's versions and with the rows of the reached stage: one row per interval over which none of them changes, with `[_valid_from, _valid_to)` and the PIT key of every version valid for the whole interval. Where the tie has no version, the row stays and the inherited keys are null, read as `[not available]`. A product's rows are rebuilt when its attributes or ties change and when a stage it reaches changes.

Rejected: one bridge row per tie version holding only the tie's other identity, leaving the version to the query, which redoes the overlap join on every question and fans out when the dimension changes inside a tie version. Rejected: following ties where several roles are identifiers; a many-to-many tie gets its own stage (#7).

## Consequences

For any instant, each identity has exactly one row in its stage. Every dimension change multiplies the rows of each entity that reaches it, bounded by the versions involved. One-to-one ties (#8) and self-ties (#10) extend which ties are followed; neither is followed yet.
