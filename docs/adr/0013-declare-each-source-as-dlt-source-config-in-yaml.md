# ADR-0013 — Declare each source as its dlt source's own configuration, in YAML

**Status:** Accepted (2026-10-31)

## Context

Until now the resources ingest lands were a Python dict beside a hand-written OData pager (ADR-0001), so adding a source object meant writing code. dlt ships declarative sources whose whole configuration is data: `rest_api` takes a dictionary of client and resources, and its other sources take plain arguments. ADR-0001's landing rules (the row as one JSON `data` column, hive partitions, a next link only to the feed's own origin, no redirects) hold for every source and must not depend on what a declaration says.

## Decision

A source is declared in YAML as the configuration of the dlt source that reads it, with dlt's own keys, verbatim. `adventure_works` is a `rest_api` source; the file names the dlt source it configures, so another kind (`sql_database`, `filesystem`) takes the same shape. What YAML cannot hold, such as a paginator class or an auth object, is registered in code under a name and referenced by that name (`paginator: odata` is the OData next-link pager with its origin guard).

The landing rules are applied in code to every resource, whatever its declaration says: rows land whole as JSON `data`, no request follows a redirect, files land in `date=/hour=` partitions, and every load is appended. A declaration that asks for another write disposition is refused.

Rejected: a schema of our own (base URL, entity set, load kind) translated into dlt's configuration, which reads more simply but is a translation layer to document, validate and extend each time a resource needs a dlt feature dlt already has.

## Consequences

dlt's documentation is the reference for what a declaration may say. The OData `$filter` of an incremental resource is visible in its declaration. Each new kind of source, and each registered name, is code; adding an object to a known source is a file.
