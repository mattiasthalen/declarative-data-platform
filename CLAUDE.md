# Working in this repository

`README.md` is the tour. This file says how the work is done.

## Read first

- `docs/adr/README.md`: every architecturally significant decision. A recorded decision is
  not re-argued; a new one gets its own ADR.
- `docs/lexicon.md`: what the words mean. `docs/assumptions.md`: what is still assumed.
- Anchor Modeling's own reference, `docs/ANCHOR.md` in
  [Roenbaeck/anchor](https://github.com/Roenbaeck/anchor), and Lars Rönnbäck's
  [anchor-snowflake-skill](https://github.com/Roenbaeck/anchor-snowflake-skill). Clone them
  read-only when you work on integrate: `GIT_LFS_SKIP_SMUDGE=1 git clone --depth 1 <url>`.

## Layout, by kind (ADR-0012)

- `contracts/`: one ODCS v3 contract per source object, snake_case names.
- `anchor/model.yaml`: the whole Anchor model, a mirror of the vendored `anchor/anchor.xsd`.
  `anchor/mappings/<anchor>.yaml`: where each anchor's attributes are loaded from.
- `src/<ingest|conform|integrate|serve>/`: the code. `src/ownership/`: which generator owns
  which folder.
- `models/<layer>/<package>/`: dbt models. A folder with a generator's `README.md` is that
  generator's: never edit it by hand; change the declarations and run `uv run task generate`.
  Hand-written models go in folders without one.
- `macros/`: the SQL the generated models call. `macros/anchor.sql` is the crt load
  (ADR-0006); `macros/batch_log.sql` the load log (ADR-0007); `macros/uss.sql` serve.

## Rules that are easy to break

- **Generated output is committed.** After changing a contract, the model, a mapping or a
  generator, run `uv run task generate` and commit the result with the change;
  `uv run task check` fails otherwise, naming the file, and CI requires it (ADR-0014).
- **Names.** Conform columns are snake_case, `__` separates concerns, platform columns are
  `_dlt__…` (ADR-0002). Integrate keeps Roenbaeck's default naming verbatim (ADR-0003).
- **No static attributes.** Every attribute in `model.yaml` has a `timeRange`.
- **One `dbt build` per target at a time.** DuckDB's file lock refuses a second; there is no
  locking of our own (A4).

## Proving a change

```sh
uv run task check   # drift: committed models that differ from the declarations
uv run pytest
```

The suite builds synthetic lakes through every layer in throwaway copies of the repo; the
end-to-end tests take minutes. `tests/judged.md` lists the two checks a reviewer judges.
