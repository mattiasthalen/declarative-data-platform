# ADR-0024 — Declare what runs and when in this repo; the infra owns only infrastructure

**Status:** Accepted (2026-11-01)

## Context

Prefect separates flows, deployments (which flow runs, with which parameters, on which schedule and concurrency) and infrastructure (server, work pools, workers). The Prefect infra lives in another repo.

## Decision

This repo declares the flows and `orchestrate/prefect.yaml`: the deployments, the hourly schedule, the concurrency limits, and the commands' timeouts as flow parameters. The infra provides the server, the work pool and its workers; the work pool's name comes from `ORCHESTRATE_WORK_POOL`, so the same `prefect.yaml` deploys locally and on the infra.

Rejected: the infra repo owning deployments and schedules (when the platform runs would change in another repo than what it runs, and the two drift).

## Consequences

A change to what runs or when is one pull request here. The infra must supply a work pool whose workers can reach the repo, the lake and the DuckDB file (A18).
