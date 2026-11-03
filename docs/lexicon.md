# Lexicon

The words someone needs defined to talk about using or developing the platform. A term earns an entry only if it is language rather than code, needs defining here, and is the one word for its concept. Anchor Modeling's own terms (anchor, attribute, knot, tie, posit, annex, positor, reliability) mean what [ANCHOR.md](https://github.com/Roenbaeck/anchor/blob/master/docs/ANCHOR.md) says and are not repeated.

**source** — A system that feeds the lake, such as `adventure_works`, declared once in its own folder of `sources/` and `contracts/`. Distinct from the dlt source it is declared with (`rest_api`), which is how it is read. See [ADR-0017](adr/0017-give-each-source-a-folder-with-one-file-per-resource.md).

**resource** — One object a *source* serves, such as its products, landed by its own pipeline into its own lake folder and named `<source>__<resource>`. Distinct from dlt's resource, the code that yields rows. See [ADR-0018](adr/0018-run-ingest-per-source-and-report-through-exit-codes.md).

**declaration** — A file a person writes to say what the platform holds and runs: a *source* and its resources in `sources/`, its contracts in `contracts/`, the Anchor model and its mappings in `anchor/`, and what runs when in `orchestrate/prefect.yaml`. Distinct from generated output, which generators write from the declarations and nobody edits by hand, and from a declaration in code. See [ADR-0012](adr/0012-lay-the-repo-out-by-kind-with-generator-owned-folders.md).

**scheduled run** — One firing of the schedule: every *source* ingested in its own flow run, then one build of the target. Distinct from a *batch*, the Anchor-writing `dbt build` it may contain. See [ADR-0021](adr/0021-ingest-each-source-in-its-own-run-then-build-once.md).

**load** — One extraction of one *resource*, as it lands in the lake, named by its dlt load id. Distinct from *batch*: one *batch* can apply several loads.

**batch** — One `dbt build` that writes Anchor rows, numbered in the load log; Anchor's Metadata value. Distinct from *load*. See [ADR-0007](adr/0007-number-loads-with-a-batch-log-in-anchor-metadata.md).

**changed-at** — When a value became true in the business, as the source says. The only time serve uses. Distinct from *positing time* and the *batch*.

**backfill** — Serve's convention that each attribute's first value has held since `0001-01-01`, so a dimension has no all-null version and no gap before a product's first *changed-at*. Integrate never backfills. Distinct from re-running ingest or a build for past periods, which orchestrators also call a backfill. See [ADR-0011](adr/0011-serve-a-uss-from-staged-bridges-unioned-by-name.md).

**positing time** — When the platform learned a value: the extraction time of the *load* that brought it. "Extracted-at" is the column, not another word for the concept.

**as known at** — Reading history as the platform knew it at a *positing time*: only what the *loads* extracted by then had stated, their *corrections* and *retractions* included. Distinct from reading it at a *changed-at*, which picks when a value was true in the business; one question can fix both. See [ADR-0033](adr/0033-expose-the-time-traveling-perspective-as-a-duckdb-table-macro-taking-a-changing-and-a-positing-time.md).

**restatement** — The same value stated again at a later *changed-at*. Distinct from a *correction*, which states another value at a *changed-at* already held.

**correction** — Another value for a *changed-at* already held; it retracts the held value and asserts the new one. Distinct from a *restatement*. See [ADR-0006](adr/0006-apply-anchor-crt-loading-rules-in-generated-sql.md).

**late arrival** — A value whose *changed-at* is earlier than the latest *changed-at* already held for that attribute. It slots into history and does not replace the current value. Distinct from a *correction*, which states another value at a *changed-at* already held.

**retraction** — An assertion at reliability 0 that withdraws a held value. Only a null in the source, or a *correction*, retracts; absence from a *load* and a failed cast do not.

**staged bridge** — One entity's bridge in the USS staging area, holding its own keys and those inherited one step away. Distinct from *the bridge*, the union of all staged bridges.

**the bridge** — The Puppini bridge in serve, the union by name of every *staged bridge*. See [ADR-0011](adr/0011-serve-a-uss-from-staged-bridges-unioned-by-name.md).

**not available** — A ghost member for a relationship that applies but has no value: a null inside a *staged bridge*. Distinct from *not applicable*.

**not applicable** — A ghost member for a relationship that does not apply to a row: a null created when *the bridge* unions stages that lack that key. Distinct from *not available*.

**drift** — Committed generated output that differs from what its generator produces now, from the declarations or, for the README's artwork, from the generator's own code: a file `generate` would rewrite, add or remove, or an *owned region* it would rewrite. `--check` reports it, and the ruleset on `main` refuses to merge it while CI's `check` job fails. See [ADR-0013](adr/0013-check-generated-output-byte-for-byte-through-the-writer-that-owns-it.md).

**owned region** — A stretch of a hand-written file, between a begin and an end marker, that one generator rewrites and `--check` compares; everything outside it belongs to whoever writes the file. See [ADR-0028](adr/0028-let-a-generator-own-a-marked-region-of-a-hand-written-file.md).
