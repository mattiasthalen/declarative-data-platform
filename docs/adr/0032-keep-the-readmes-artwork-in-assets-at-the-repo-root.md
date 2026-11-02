# ADR-0032 — Keep the README's artwork in assets/ at the repo root

**Status:** Proposed (2026-11-02) · **Supersedes:** the location decision (under `docs/`) in [ADR-0029](0029-ship-the-readmes-artwork-as-svg-committed-under-docs.md)

## Context

ADR-0029 decided the README's artwork is SVG, one file per image, committed under `docs/`, and #37 put the hero at `docs/hero.svg`. Story #38 animates the hero, and its motion has nine tiles each moving through four stage layouts; a script now writes the file from those layouts, and the committed file is generated output. ADR-0012 lets a generator write only into a folder that carries its README marker, and `docs/` holds hand-written records (ADRs, the lexicon, assumptions) that no generator may touch. The artwork needs a folder of its own, and #39's longer video will sit beside the hero.

## Decision

The README's artwork lives in `assets/` at the repository root, referenced from the README by a relative path (`assets/hero.svg`). The rest of ADR-0029 stands: SVG, one file per image, committed in the repository.

Rejected: `docs/artwork/`, which keeps ADR-0029 true as written but puts generated files inside the folder of hand-written records; `docs/hero.svg` with the file marked as generated, which needs an ownership kind the writer does not have (a per-file marker, rejected in ADR-0012 because one edited header hides a file from cleanup).

## Consequences

`assets/` is generated output: its README marker names the generator that owns it, and nothing in it is edited by hand. Every reference to `docs/hero.svg` (the README, the hero tests, the judged rubrics) moves to `assets/hero.svg`. Artwork that is not generated would need a folder of its own, since a generator removes any file it did not write.
