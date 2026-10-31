# Judged checks for S1

Two edge cases are judged at review rather than run. The reviewer reads the
generated output and the code, and records pass or fail for each line below.

## EC6: two loads in the same second

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
