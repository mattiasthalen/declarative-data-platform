# Working in this repository

`README.md` is the tour. This file says how the work is done, wherever you are in the repo.

## Read first

- `docs/adr/README.md`: every architecturally significant decision. A recorded decision is
  not re-argued; a new one gets its own ADR.
- `docs/lexicon.md`: what the words mean. `docs/assumptions.md`: what is still assumed.

## Where things are, and whose rules apply

The repo is laid out by kind, and each layer's files sit in folders named after the layer
(ADR-0012, ADR-0015). Each layer has its own rules in `.claude/rules/`, which load by
themselves when you read a file of that layer:

| layer | its folders | its rules |
|---|---|---|
| ingest | `**/ingest/`, `sources/` | `.claude/rules/ingest.md` |
| conform | `**/conform/`, `contracts/`, `models/raw/` | `.claude/rules/conform.md` |
| integrate | `**/integrate/`, `anchor/` | `.claude/rules/integrate.md` |
| serve | `**/serve/` | `.claude/rules/serve.md`, and `.claude/rules/uss.md` for all but the hand-written models |

`**/<layer>/` means that layer's folder under `src/`, `models/`, `macros/` and `tests/`. A new
file of a layer goes in one of its folders, or its rules will not reach the next agent (A11).
Files outside them, such as `src/ownership/`, `macros/generate_schema_name.sql` or
`orchestrate/` (the Prefect flows and `prefect.yaml` of the scheduled run), serve every layer
and follow only this file. `src/simulate/` is the change simulator, a tool that writes
Products and ProductSubcategories loads into the lake; it is not ingest, which names no resource (ADR-0016, ADR-0027).

## Rules that hold everywhere

- **Generated output is committed.** After changing a contract, the model, a mapping or a
  generator, run `uv run task generate` and commit the result with the change;
  `uv run task check` fails otherwise, naming the file, and CI requires it (ADR-0014).
- **Never edit a generated folder by hand.** A folder under `models/`, or `assets/`, whose
  `README.md` a generator wrote is that generator's; change what it is written from (the
  declarations, or `src/artwork/` for `assets/`) and regenerate (ADR-0012, ADR-0032).
  The same holds between the `erd:<layer>` markers in the root README (ADR-0028).
- **`__` separates concerns in every name**: schemas (`serve__uss`), models
  (`adventure_works__products`), columns (`_dlt__load_id`).
- **One `dbt build` per target at a time.** DuckDB's file lock refuses a second. Scheduled
  runs are held to one by `orchestrate/prefect.yaml`; a hand-run build is not (A4).

## Proving a change

```sh
uv run task check   # drift: committed generated output that differs from its generator
uv run pytest
```

The suite builds synthetic lakes through every layer in throwaway copies of the repo; the
end-to-end tests take minutes. It runs across one pytest-xdist worker per CPU, so each test
must stand alone (A26); `uv run pytest -n 0` runs it serially, for debugging.
`tests/judged.md` lists the checks a reviewer judges.

After changing anything in `.claude/rules/` or moving a layer's folders, also run
`uv run task test-rules`: it opens a file of each layer in a real Claude Code session and
checks which rules loaded. It needs Claude Code, logged in, and never runs in CI.
