# ADR-0012 — Lay the repo out by kind, and let a generator own only folders that carry its README

**Status:** Accepted (2026-10-31); partly superseded by [ADR-0015](0015-keep-each-layers-files-in-layer-named-folders-and-scope-agent-rules-to-them.md) (where macros live, 2026-10-31)

## Context

Declarations are the only authored artefacts, generators turn them into committed dbt SQL, and serve will also hold some hand-written models. A generator must remove what it no longer emits without ever touching hand-written work.

## Decision

The repo is laid out by kind: `src/{ingest,conform,integrate,serve}/` for code, `contracts/` and `anchor/` (`model.yaml`, `mappings/`) for declarations, `models/<layer>/<package>/` for dbt models, `macros/`, `tests/`, and later `orchestrate/`. A generator owns a package folder only when that folder holds a `README.md` the generator wrote, saying which generator wrote it, from what, and not to edit it. It rewrites its own folders whole and removes stale files, and refuses a folder with no such README or another generator's.

Rejected: folders by step (`1_ingest` … `4_serve`), which spreads authored and generated files across every step and makes digit-led package names; a nested `generated/` folder, which deepens every path; per-file headers, where one edited header hides a file from cleanup.

## Consequences

Authored and generated files are apart at a glance, which story 2's `--check` relies on. Hand-written models live in folders without a generator's README.

## Addendum 2026-10-31

Ingest declarations live in a top-level `sources/`, and `sources/` and `contracts/` hold one folder per source with one file per resource (ADR-0014).
