# ADR-0025 — Keep one uv project, with orchestrate as a dependency group

**Status:** Accepted (2026-11-01)

## Context

Prefect brings a large dependency tree beside dbt-core and dlt. At Bannerflow, an infra Prefect repo cloning the dbt repo meant two lockfiles and dependabot updating the same packages in both.

## Decision

The repo stays one uv project: Prefect is the `orchestrate` dependency group in the root `pyproject.toml`, beside `ingest`, `dbt` and `dev`, in one `uv.lock`.

Rejected: a separate uv project in `orchestrate/` (two lockfiles that drift and are updated twice).

## Consequences

Prefect's pins must resolve with dbt's and dlt's (A19); a conflict is settled in one lock, not hidden across two.
