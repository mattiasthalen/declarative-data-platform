# ADR-0023 — Orchestrate with Prefect

**Status:** Accepted (2026-11-01)

## Context

The ticket names Kestra as the first candidate and asks for a comparison with a lighter option. Mattias already runs a Prefect infrastructure (server, work pools, workers) that only needs flows supplied. The flows must fan out one pod per source (ADR-0021) and be provable end to end from a development container.

## Decision

Prefect runs the platform's schedule, with three deployments: `run` (scheduled), `ingest-source` and `build`. `run` starts the other two as flow runs of their own deployments, so each runs in its own process on a local process pool, and could run on its own pod once a Kubernetes pool gets the repo, the lake and the DuckDB file (deferred to multi-environment deploys).

Rejected: Kestra (pure YAML and one container, but its image could not be pulled into the development container, so the story could not be proven, and no Kestra infra exists); cron (no fan-out, no run history, no pod per source).

## Consequences

The flows are Python; the declaration that says what runs and when, `orchestrate/prefect.yaml`, stays YAML. Prefect's dependencies join the repo's lock (A19).
