# ADR-0016 — Fetch incremental resources from their last cursor value inclusive

**Status:** Accepted (2026-10-31)

## Context

Some resources are too large to pull whole every run and are fetched incrementally on a cursor such as `ModifiedDate`. AdventureWorks' cursors are plain dates: many rows share a value, and more can arrive with the last value seen after a run has read it. ADR-0006's load writes nothing for an identical value at a ChangedAt it already holds, and ADR-0009 lets conform append repeats for Anchor to discard.

## Decision

An incremental resource asks for rows whose cursor is greater than or equal to the last value it saw (`ModifiedDate ge {incremental.start_value}`), and dlt keeps that value in the resource's pipeline state in the lake. The feed serves the rows at the last value again; dlt drops those it already landed unchanged and lands the rest.

Rejected: strictly greater than, which never lands a row that arrives later with the last value seen.

## Consequences

No row is lost to a shared cursor value, and an unchanged row is not landed twice: dlt keeps a hash of each row at the last value in the same state. A row changed without moving its cursor lands again, which conform appends and Anchor treats by its rules (ADR-0006). A run with nothing new lands no load. The state lives in `$LAKE_ROOT/_dlt/`, so a pod with no local dlt folder resumes from the lake, and deleting that folder makes the next load start over from the initial value.
