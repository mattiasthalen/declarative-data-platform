# ADR-0013 — Keep each layer's files in folders named after the layer, and scope agent rules to them

**Status:** Accepted (2026-10-31) · **Supersedes:** the where-macros-live decision in [ADR-0012](0012-lay-the-repo-out-by-kind-with-generator-owned-folders.md)

## Context

ADR-0012 lays the repo out by kind, so one layer spans several folders (conform is `contracts/`,
`src/conform/`, `models/raw/`, `models/conform/`), and it kept every macro flat in `macros/`.
Agents working in the repo need each layer's rules when, and only when, they touch that layer's
files. Claude Code loads a nested CLAUDE.md for the folder a file sits in, and a
`.claude/rules/*.md` file whenever a file matching one of its `paths:` patterns is read.

## Decision

A layer's files live in folders named after the layer: `src/<layer>/`, `models/<layer>/`,
`macros/<layer>/`, `tests/<layer>/`, plus the declarations (`contracts/` and `models/raw/` for
conform, `anchor/` for integrate). Only macros serving every layer (`generate_schema_name.sql`) stay
at the root of `macros/`.

Each layer's agent rules live in one `.claude/rules/<layer>.md`, scoped by `paths:` patterns on
those folder names (`**/conform/**`, `contracts/**`, `models/raw/**`). The USS has its own
`uss.md` inside serve, because serve also holds hand-written models. The root CLAUDE.md routes to
them and holds only what is true everywhere.

Rejected: a nested CLAUDE.md in each layer folder, which needs a pointer file per folder and cannot
split a shared `macros/`; listing a layer's files one by one in its patterns, with a test that
places every tracked file, which is upkeep that layer-named folders make unnecessary.

## Consequences

A new file of a layer gets that layer's rules by being put where it belongs; a file put elsewhere
silently gets none (A8). Rules are tied to Claude Code's rules mechanism (A7), proved by a local
test (`task test-rules`) that runs real Claude sessions and never runs in CI. Other agents do not
read `.claude/rules/`.
