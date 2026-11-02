# ADR-0014 — Require CI's check and test jobs to pass before anything merges into main

**Status:** Accepted (2026-10-31)

## Context

Drift between declarations and committed generated code ([ADR-0013](0013-check-generated-output-byte-for-byte-through-the-writer-that-owns-it.md)) is only prevented if a failing check stops a merge. The repository is on GitHub, allows merge commits only, and had no CI. The full test suite builds synthetic lakes through every layer and takes about 4.5 minutes; the check takes under a minute.

## Decision

One GitHub Actions workflow runs on every pull request and every push to `main`, with two parallel jobs: `check` runs `task check`, and `test` runs `uv run pytest`, whose end-to-end tests are the `dbt build` against a lake. Both use `astral-sh/setup-uv` with its cache and Python 3.13, and neither calls the live source. A branch ruleset on `main` requires both jobs to pass before a merge, each pinned to the GitHub Actions app so a status of the same name from elsewhere does not count. The workflow's token is read-only, actions are pinned by commit, and uv runs with the lock as committed.

Rejected: advisory CI, because a red pull request could still merge; one job running the check and then the tests, because a drift would hide test failures and the red would arrive later.

## Consequences

A pull request cannot merge while drifted or red. Job names `check` and `test` are part of the ruleset: renaming a job means updating the ruleset in the same change. Anyone with admin rights can switch the ruleset off in the repository settings. Story 2's second delivery replaces the synthetic lake with the seeded simulator's lake inside the same `test` job. Rulesets on a private repository need a paid GitHub plan (A9); without one CI is advisory again.

## Addendum (2026-11-01, story #25)

The seeded simulator's lake (ADR-0027) runs beside the hand-written synthetic lakes in the same `test` job, not instead of them: each hand-written lake pins one exact scenario, while the simulated lake checks that a longer, seeded history builds and answers the business question.

## Addendum 2026-11-02

The `test` job's `uv run pytest` runs the suite across one pytest-xdist worker per CPU (`-n auto` in `addopts`). On a 4-core `ubuntu-latest` runner the job took a median of 6 min 39 s over three attempts on PR #41 (7 min 42 s, 6 min 28 s, 6 min 39 s), against 14 min 06 s serially on its base on `main`.
