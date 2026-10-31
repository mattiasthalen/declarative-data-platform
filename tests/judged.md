# Judged checks for S1

Two edge cases are judged at review rather than run. The reviewer reads the
generated output and the code, and records pass or fail for each line below.

## EC6: two loads at one PositedAt

Two loads that share a `_dlt__extracted_at` and carry different values for one
version (same product, same attribute, same ChangedAt) are two assertions of one
version by one positor at one PositedAt. The build fails on that contradiction
([8]). It does not pick one.

Pass when all of these hold:

1. The generated Anchor load SQL (the integrate posit/annex models, or the
   macros they call) detects more than one distinct value for one
   (PR_ID, attribute, ChangedAt, PositedAt, Positor) among the rows it is about
   to assert.
2. On that condition it raises: a DuckDB `error(...)`, a failing cast, a
   uniqueness or primary-key violation, or a dbt `raise_compiler_error` or
   error-severity test that stops the integrate models from committing. The
   build exits non-zero.
3. No `qualify row_number() ... = 1`, `any_value`, `max`, `min`, `first`,
   `last`, `arg_max` or `distinct on` picks a winner among such rows before
   that check runs. Deduplication of rows that are identical in value is fine.
4. Loads with different `_dlt__extracted_at` still apply oldest first. The check
   in (1) groups by PositedAt, so it does not fire for EC2's two loads.

## EC8: two builds on one target at once

DuckDB lets one writer hold a database file. A second `dbt build` on the same
target fails to open the file and changes nothing. We accept this and add no
locking of our own ([19]).

Pass when all of these hold:

1. No lock files, PID files, advisory locks, retry loops or waits on the
   DuckDB file appear in `src/`, `macros/`, the Taskfile or `profiles.yml`.
   Search for `lock`, `flock`, `fcntl`, `portalocker`, `filelock`, `.pid` and
   `retry`.
2. Nothing catches the DuckDB `IOException` ("Could not set lock on file") and
   swallows it or turns it into a success. The second `dbt build` exits
   non-zero with DuckDB's own message in its output.
3. Optional live confirmation: start `uv run dbt build --target dev`, and while
   it runs start a second one in another shell. The second fails with the lock
   error. The first completes and the load log shows one batch for it.

# Judged checks for story #12

## No rule stated twice (AC4, AC5, AC6)

The six files are the root `CLAUDE.md` and `.claude/rules/{ingest,conform,integrate,serve,uss}.md`.
The reviewer reads all six and `main`'s `CLAUDE.md` (from before the story), and records pass
or fail for each line below with the table that supports it.

Pass when all of these hold:

1. **One home per rule (AC4).** List every rule stated in the six files, one row each, with
   the file that states it. A rule is a constraint on how work is done, whatever its
   wording: a reworded or partial restatement in a second file counts as the same rule.
   Fail on any rule that appears in two files. A pointer that only names another file
   ("see `.claude/rules/integrate.md`") is not a rule.
2. **Layer files hold only their layer (AC4, AC6).** No rules file states something true of
   every layer (generated output is committed, `__` separates concerns, one `dbt build` per
   target, how to prove a change, read-first documents): those live in the root `CLAUDE.md`.
   Each rules file states only what holds for files matching its own `paths:`. `serve.md`
   states nothing specific to the USS (bridges, relationship steps, ghost rows), so it does
   not mislead a hand-written serve model; `uss.md` holds those.
3. **Every rule links its ADR (AC6).** Each rule in a rules file that an ADR decided links
   that ADR (by number, as a link into `docs/adr/`). A rule with no deciding ADR is fine
   unlinked; name it in the table so the reviewer's claim that no ADR exists is visible.
4. **Nothing lost (AC5).** Map each bullet and each sentence-level rule of `main`'s
   `CLAUDE.md` to its row in the table from (1). Fail on any that has no home. The one
   permitted loss is the reference to Lars Rönnbäck's anchor-snowflake-skill;
   `docs/ANCHOR.md` in Roenbaeck/anchor stays the integrate reference.
   `! grep -rn anchor-snowflake-skill CLAUDE.md .claude/` exits 0
   (`tests/test_rules_files.py` also checks this).
5. **The router routes.** The root `CLAUDE.md` says that the layer rules live in
   `.claude/rules/` and load by path, so a reader of the root file knows where the rest is.

# Judged checks for story #17 (ingest declared)

Two acceptance criteria of story #17 are judged at review. The reviewer reads the
files named and records pass or fail for each.

## AC18: the business question on TransactionHistories

`sources/adventure_works/transaction_histories.yaml` records the approved business
question (design tree B9, Mattias 2026-10-31) in a comment block.

Pass when all of these hold:

1. The question is there word for word: "What is the total quantity of units sold
   per calendar month and product line?"
2. The block states each part of its anatomy: aggregation sum; measure `Quantity`;
   dimensions calendar month and product line; time every month the source holds
   (2013-07..2014-08).
3. The block carries the three definitions, in B9's words:
   - sold = TransactionType `S` (74,575 rows; `W` work orders and `P` purchases
     are not sales);
   - calendar month = month of `TransactionDate` (business date, not ModifiedDate
     or extraction);
   - product line = the product's line as of the transaction date, trimmed code,
     empty its own group.
4. Nothing in the block contradicts B9 or adds a definition B9 does not make, and
   the comment is a comment: the file still parses to the same dlt resource entry
   with it removed.

## AC20: the docs drafted in the design interview

The run folder's `docs/` (`doc-changes.md` and `adr/`) holds the drafts. Compare
the repo against them.

Pass when all of these hold:

1. `docs/adr/` holds ADR-0013 to ADR-0016 with the drafts' title, status, context,
   decision, rejected alternatives and consequences. Renumbering after a collision
   with a parallel story is fine when the links follow. A wording change is fine
   only where the build proved a draft wrong (the plan names ADR-0016's
   consequence sentence on repeats at the cursor boundary); it says what changed.
2. `docs/adr/README.md` has the four index rows.
3. ADR-0001 and ADR-0012 each end with the drafted `## Addendum 2026-10-31`, and
   their original text is otherwise unchanged.
4. `docs/lexicon.md` has the entries *source* and *resource* as drafted, and no
   other entry changed.
5. `docs/assumptions.md` has A7 and A8 as drafted, and the measured facts of
   2026-10-31 (the `$filter`/`$orderby`/`$top`/`$select`/`$count` support and the
   TransactionHistories row counts and date range).
6. Nothing in the repo's docs still says resources are declared in Python or that
   contracts sit flat in `contracts/*.yaml`.
