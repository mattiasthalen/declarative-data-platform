# ADR-0014 — Require CI's check and test jobs to pass before anything merges into main

**Status:** Accepted (2026-10-31)

## Context

Drift between declarations and committed generated code ([ADR-0013](0013-check-generated-output-byte-for-byte-through-the-writer-that-owns-it.md)) is only prevented if a failing check stops a merge. The repository is on GitHub, allows merge commits only, and had no CI. The full test suite builds synthetic lakes through every layer and takes about 4.5 minutes; the check takes under a minute.

## Decision

One GitHub Actions workflow runs on every pull request and every push to `main`, with two parallel jobs: `check` runs `task check`, and `test` runs `uv run pytest`, whose end-to-end tests are the `dbt build` against a lake. Both use `astral-sh/setup-uv` with its cache and Python 3.13, and neither calls the live source. A branch ruleset on `main` requires both jobs to pass before a merge.

Rejected: advisory CI, because a red pull request could still merge; one job running the check and then the tests, because a drift would hide test failures and the red would arrive later.

## Consequences

A pull request cannot merge while drifted or red. Job names `check` and `test` are part of the ruleset: renaming a job means updating the ruleset in the same change. Anyone with admin rights can switch the ruleset off in the repository settings. Story 2's second delivery replaces the synthetic lake with the seeded simulator's lake inside the same `test` job.
