# Assumptions

What the design still assumes, and how you would know it stopped holding; then facts measured against live data.

## Standing

| id | assumption | area | how you would know it stopped holding |
|---|---|---|---|
| A1 | A full pull of Products is small enough to repeat every run. | ingest | A Products load takes more than a minute or the lake grows past a few hundred MB. |
| A2 | `ModifiedDate` moves whenever a Product value changes in the source. | integrate | A load holds a different value for a product with an unchanged `ModifiedDate` more often than rarely: corrections pile up in the annexes. |
| A3 | dlt's load id is fractional epoch seconds as text, increasing with time. | conform | `try_cast` of `_dlt_load_id` to a number fails, or a later load has a smaller id. |
| A4 | Only one `dbt build` runs against a target at a time, and none runs while ingest is landing a load. | operations | The orchestrator (story 16) schedules overlapping runs, or a staged load has fewer rows than its files in the lake. |
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

## Measured (2026-10-30, the AdventureWorks OData feed)

- The feed pages at 500 rows via `@odata.nextLink`.
- Field names are PascalCase with `Id` (not `ID`): `ProductId`, `ProductSubcategoryId`, `ProductModelId`, `Rowguid`. `json_extract_string` matches names case-sensitively.
- Dates are plain `YYYY-MM-DD` with no time or offset, `ModifiedDate` included (2026-10-31).
- Products: 504 rows; every `ModifiedDate` is 2014-02-08.
- `ProductLine` is padded (`'R '`, `'M '`, `'T '`, `'S '`) or null (225 rows). `Color` is null for 247. `SellEndDate` is null for 402.

## Measured (2026-10-31, CI)

- The `test` job on a GitHub-hosted `ubuntu-latest` (Ubuntu 26.04) runner: 118 passed, 1 skipped, job 3 min 47 s (PR #22, run 41252831815). The `check` job: 12 s.

## Measured (2026-10-31, the AdventureWorks OData feed)

- `$filter=ModifiedDate gt <date>` and `ge` work; `$orderby`, `$top`, `$select` and `$count=true` work.
- TransactionHistories: 113,443 rows, `TransactionDate` 2013-07-31 to 2014-08-03, `ModifiedDate` equal to `TransactionDate` on the rows sampled; `TransactionType` `S` 74,575, `W` 31,002, `P` 7,866.
- The next link carries the request's `$filter` and adds `$skip=500`, with no `$orderby`; dlt's next-link paginator sends the next page without the declared params, so the feed's own copy of `$filter` is what holds.
- On every incremental load dlt logs that the cursor column (`modified_date`) received no data: it hints the cursor as a column, but rows land wrapped in `data`. Harmless.
