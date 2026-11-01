# Assumptions

What the design still assumes, and how you would know it stopped holding; then facts measured against live data.

## Standing

| id | assumption | area | how you would know it stopped holding |
|---|---|---|---|
| A1 | A full pull of Products is small enough to repeat every run. | ingest | A Products load takes more than a minute or the lake grows past a few hundred MB. |
| A2 | `ModifiedDate` moves whenever a Product value changes in the source. | integrate | A load holds a different value for a product with an unchanged `ModifiedDate` more often than rarely: corrections pile up in the annexes. |
| A3 | dlt's load id is fractional epoch seconds as text, increasing with time. | conform | `try_cast` of `_dlt_load_id` to a number fails, or a later load has a smaller id. |
| A4 | Only one `dbt build` runs against a target at a time, and none runs while ingest is landing a load. A scheduled run orders its own ingest before its own build, and `orchestrate/prefect.yaml` holds Prefect to one `run` and one `build` at a time (ADR-0026); a `build` started by hand in Prefect queues behind the scheduled `build` but is not held off the scheduled ingest, and an `ingest-source` started by hand in Prefect, or anything started with `task`, is held off nothing. | operations | A hand-started build or ingest overlaps a scheduled run, or a staged load has fewer rows than its files in the lake. |
| A5 | The generated load writes each posit and annex key once; nothing in DuckDB enforces it, since no model declares a contract or constraint. | integrate | `IntegrityViolations` reports a duplicate key and its `empty` test fails the build. |
| A6 | Source dates and timestamps carry no timezone offset. `try_cast` to timestamp drops an offset without converting. | conform | A contract's source serves a value with `Z` or `+hh:mm`. |
| A7 | CI needs no network beyond GitHub and the Python package index; nothing in `pytest` or `task check` calls the live source. | ci | A CI run fails on a connection error to a source host, or a test needs `demodata.grapecity.com`. |
| A8 | The full suite runs on a GitHub-hosted runner in well under 15 minutes. | ci | The `test` job takes longer than 15 minutes, or hits its 30-minute timeout. |
| A9 | The `main` ruleset is enforced: the repository is public, or its owner's plan includes rulesets on private repositories. | ci | Creating the ruleset is refused, or a pull request with a red `check` can be merged. |
| A10 | Claude Code loads a `.claude/rules/*.md` file when the agent reads a file matching one of its `paths:` patterns, and reports it to the `InstructionsLoaded` hook. Claude Code drops a trailing `/**`, so `anchor/**` matches an `anchor` folder at any depth and `/anchor/**` only the root one (probed on 2.1.316). | harness | `uv run task test-rules` fails after a Claude Code update. |
| A11 | Every file of a layer sits under a folder named after the layer, or under that layer's declarations (`contracts/`, `models/raw/`, `anchor/`). | harness | A layer's file is found outside them, and an agent edits it without its rules. |
| A12 | `ModifiedDate` on TransactionHistories moves whenever a row is added or changed, and is never set earlier than the cursor already read. | ingest | A full pull holds a row, or a changed value, that the incremental loads never landed. |
| A13 | dlt restores a resource's pipeline state, its incremental cursor included, from the lake's `_dlt/` when the run has no local dlt folder. | ingest | A second run in a fresh pod fetches the whole TransactionHistories feed again. |
| A14 | dlt's incremental drops a row at the last cursor value that it already landed unchanged, by a hash it keeps in the pipeline state. | ingest | Every run lands the rows at the last cursor value again; conform appends them and Anchor discards them (ADR-0006), so only volume grows. |
| A15 | dlt keeps a resource's incremental step where it is when ingest adds the JSON wrap after it with `add_map(..., insert_at=len(resource._pipe))`; `_pipe` is private to dlt. | ingest | After a dlt upgrade the wrap runs before the incremental, which finds no cursor: AC8 and AC9 fail with `IncrementalCursorPathMissing`. |
| A16 | Ingest and its tasks run from the repo root: `sources/` and the default `lake/` are read relative to the working directory. | ingest | Run elsewhere, ingest finds no source and exits 2, or lands in another folder's lake. |
| A17 | The feed's page order holds between the requests of one load: its next link pages by `$skip` with no `$orderby`. | ingest | A row that moves between pages mid-load lands twice or not at all in that load. |
| A18 | A flow run starts in the directory `prefect deploy` ran from (the repo root, through `task orchestrate:deploy`), and the work pool's workers have the repo at that path, with the lake and the DuckDB file reachable from it. The pool admits one flow run more than there are sources, since `run` waits on its children while they all ingest at once; a child that cannot start within 10 minutes is cancelled. Anyone who can create a flow run can choose the commands it runs (the command parameters, ADR-0024), so Prefect API access is code execution on the workers. | orchestrate | An `ingest-source` or `build` run fails on a missing file or builds an empty lake; children of `run` stay Scheduled until `run` cancels them. |
| A19 | Prefect resolves alongside dbt-core and dlt in one lock. | orchestrate | `uv lock` fails, or pins dbt-core or dlt outside their ranges in `pyproject.toml`. |
| A20 | The committed Products snapshot is representative of the live feed: same fields, same quirks. | simulate | The live feed's measured facts change (row count, a field added or renamed, product lines no longer padded) and `src/simulate/adventure_works__products.jsonl` was not refreshed. |
| A21 | The simulated lake's history exercises the crt rules CI cares about: every change kind lands at least once in CI's seeded run. | ci | The CI seed's run lands no row of some change kind (`tests/simulate/test_simulate.py::test_change_kinds` fails on it). |
| A22 | GitHub's Mermaid renders the README's `erDiagram`s: parenthesised types (`varchar(25)`, any version), names with a leading underscore (`_bridge`, Mermaid 10.5 and later) and quoted comments; a comma in a type (`decimal(10,2)`) needs Mermaid 11.16 and later, and no model declares one yet. | docs | The README on GitHub shows a Mermaid error box instead of a diagram. |
| A23 | GitHub renders an SVG README image that carries its fonts as `data:` URIs in `@font-face`: in those fonts, with no outside fetch, in both its light and dark theme. | docs | The hero on github.com shows Georgia or a sans fallback in the wordmark, or no image. |

## Measured (2026-10-30, the AdventureWorks OData feed)

- The feed pages at 500 rows via `@odata.nextLink`.
- Field names are PascalCase with `Id` (not `ID`): `ProductId`, `ProductSubcategoryId`, `ProductModelId`, `Rowguid`. `json_extract_string` matches names case-sensitively.
- Dates are plain `YYYY-MM-DD` with no time or offset, `ModifiedDate` included (2026-10-31).
- Products: 504 rows; every `ModifiedDate` is 2014-02-08.
- `ProductLine` is padded (`'R '`, `'M '`, `'T '`, `'S '`) or null (225 rows). `Color` is null for 247. `SellEndDate` is null for 402.

## Measured (2026-11-01, the AdventureWorks OData feed)

- Products: 504 rows, every `ModifiedDate` 2014-02-08; `ProductLine` null for 226, `Color` for 248, `SellEndDate` for 406 (the 2026-10-30 counts above were off by a few). The committed snapshot, `src/simulate/adventure_works__products.jsonl`, matches the feed row for row.

## Measured (2026-10-31, CI)

- The `test` job on a GitHub-hosted `ubuntu-latest` (Ubuntu 26.04) runner: 118 passed, 1 skipped, job 3 min 47 s (PR #22, run 41252831815). The `check` job: 12 s.

## Measured (2026-10-31, the AdventureWorks OData feed)

- `$filter=ModifiedDate gt <date>` and `ge` work; `$orderby`, `$top`, `$select` and `$count=true` work.
- TransactionHistories: 113,443 rows, `TransactionDate` 2013-07-31 to 2014-08-03, `ModifiedDate` equal to `TransactionDate` on the rows sampled; `TransactionType` `S` 74,575, `W` 31,002, `P` 7,866.
- The next link carries the request's `$filter` and adds `$skip=500`, with no `$orderby`; dlt's next-link paginator sends the next page without the declared params, so the feed's own copy of `$filter` is what holds.
- On every incremental load dlt logs that the cursor column (`modified_date`) received no data: it hints the cursor as a column, but rows land wrapped in `data`. Harmless.
