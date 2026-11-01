# Lexicon

The words someone needs defined to talk about using or developing the platform. A term earns an entry only if it is language rather than code, needs defining here, and is the one word for its concept. Anchor Modeling's own terms (anchor, attribute, knot, tie, posit, annex, positor, reliability) mean what [ANCHOR.md](https://github.com/Roenbaeck/anchor/blob/master/docs/ANCHOR.md) says and are not repeated.

**load** — One extraction of one resource, as it lands in the lake, named by its dlt load id. Distinct from *batch*: one *batch* can apply several loads.

**batch** — One `dbt build` that writes Anchor rows, numbered in the load log; Anchor's Metadata value. Distinct from *load*. See [ADR-0007](adr/0007-number-loads-with-a-batch-log-in-anchor-metadata.md).

**changed-at** — When a value became true in the business, as the source says. The only time serve uses. Distinct from *positing time* and the *batch*.

**positing time** — When the platform learned a value: the extraction time of the *load* that brought it. "Extracted-at" is the column, not another word for the concept.

**restatement** — The same value stated again at a later *changed-at*. Distinct from a *correction*, which states another value at a *changed-at* already held.

**correction** — Another value for a *changed-at* already held; it retracts the held value and asserts the new one. Distinct from a *restatement*. See [ADR-0006](adr/0006-apply-anchor-crt-loading-rules-in-generated-sql.md).

**retraction** — An assertion at reliability 0 that withdraws a held value. Only a null in the source, or a *correction*, retracts; absence from a *load* and a failed cast do not.

**staged bridge** — One entity's bridge in the USS staging area, holding its own keys and those inherited one step away. Distinct from *the bridge*, the union of all staged bridges.

**the bridge** — The Puppini bridge in serve, the union by name of every *staged bridge*. See [ADR-0011](adr/0011-serve-a-uss-from-staged-bridges-unioned-by-name.md).

**not available** — A ghost member for a relationship that applies but has no value: a null inside a *staged bridge*. Distinct from *not applicable*.

**not applicable** — A ghost member for a relationship that does not apply to a row: a null created when *the bridge* unions stages that lack that key. Distinct from *not available*.

**drift** — Committed generated output that differs from what the declarations produce now: a file `generate` would rewrite, add or remove. `--check` reports it, and the ruleset on `main` refuses to merge it while CI's `check` job fails. See [ADR-0013](adr/0013-check-generated-output-byte-for-byte-through-the-writer-that-owns-it.md).
