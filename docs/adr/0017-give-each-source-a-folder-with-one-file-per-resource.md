# ADR-0017 — Give each source a folder in `sources/` and `contracts/`, one file per resource

**Status:** Accepted (2026-10-31)

## Context

ADR-0012 lays the repo out by kind, with declarations at the top level and code under `src/`, and kept contracts flat in `contracts/` (`adventure_works__products.yaml`). Ingest declarations (ADR-0016) are a new kind of declaration, and a second resource of the same source arrives with them.

## Decision

Ingest declarations live in a top-level `sources/`, one folder per source. In it, `_source.yaml` holds what every resource shares (the client: base URL, paginator), and each resource has its own file holding its dlt resource entry, named for the resource: `sources/adventure_works/products.yaml`. Contracts follow the same shape: `contracts/adventure_works/products.yaml`. A resource's lake folder, pipeline and contract id stay `<source>__<resource>`, derived from the two names.

Rejected: declarations inside `src/ingest/`, the only declaration that would sit with code; one file per source holding every resource, which grows with the source and puts unrelated resources in one diff.

## Consequences

Adding an object is one file in `sources/<source>/` and, when it is staged, one in `contracts/<source>/` with the same name. The underscore keeps `_source.yaml` apart from resource files; no resource may be named `_source`. Tools that glob `contracts/*.yaml` look one folder down.
