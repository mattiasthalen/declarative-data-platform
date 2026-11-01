# ADR-0026 — Let a generator own a marked region of a hand-written file

**Status:** Accepted (2026-11-01)

## Context

Generators own whole package folders under `models/`, marked by a README they wrote (ADR-0012), and `generate --check` compares every byte they would write through the same writer (ADR-0013). Story 3 wants each layer's logical model as a Mermaid `erDiagram` in the root README, kept current by that layer's generator. The root README is hand-written: no generator can own the file, and a hand edit outside the diagrams must never be overwritten or reported as drift.

## Decision

The ownership writer also owns regions: a stretch of a hand-written file between a begin and an end marker, each an HTML comment naming the region and the generator that writes it (`<!-- erd:<layer> begin … -->`, `<!-- erd:<layer> end -->`). A generator replaces the text between its own markers and leaves every other byte of the file as it is. `--check` compares the file as the generator would leave it with the committed file, and reports a stale region as `changed <file>` with its diff, like any other drift. A missing file, a missing, duplicated or reversed marker refuses the run with exit 2, naming the marker, before anything is written, the generator's folders included. The person who writes the file places the markers once; the generator never adds or moves them.

Rejected: a fourth generator that reads every layer's declarations and writes the README, because each layer's generator should be the only reader of its declarations; each diagram in its generated folder's own README with links from the root, which needs no new mechanism but leaves the root README without the model; a generated README with hand-written parts kept in a template, which moves the README's prose out of the file people edit.

## Consequences

The first owned region is the root README's "The model" section, one region each for conform, integrate and serve. Any generator can now keep a passage of documentation current, and drift in it fails CI's `check` job (ADR-0014). A hand edit inside a region is drift and is reverted by `task generate`. Deleting a marker breaks `generate` for that layer until it is restored, so the markers are part of the README's contract with the generators.
