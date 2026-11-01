# ADR-0013 — Check generated output byte for byte through the writer that owns it

**Status:** Accepted (2026-10-31)

## Context

Generated dbt models are committed (ADR-0012), and the declarations must stay their only source. A committed file can drift from what its generator writes: someone edits it by hand, or changes a contract, the model or a mapping without regenerating. All three generators (conform, integrate, serve) already write through one function in `src/ownership`, which works out which files in the folders a generator owns it would rewrite, add or remove.

## Decision

Each generator takes `generate --check`. The check runs the same planning as `generate` through the same ownership writer, writes nothing, and compares bytes: a file whose text would change, a file that would be added, and a stale file or folder that would be removed each count as drift. Hand-written folders are never read. It prints one line per drifted path (`changed <path>`, `missing <path>`, `stale <path>`), a unified diff under each changed file capped at about 40 lines, and a summary that names `task generate`. It exits 0 with no output when clean, 1 on drift, and 2 when a declaration is invalid or a folder is refused. `task check` runs all three and reports every layer even after one fails.

Rejected: a normalized comparison (ignoring whitespace or line endings), because the generators write exact text and normalization would hide real drift; a separate diff in each generator, because three copies of the comparison can disagree with the one writer; names only, without a diff, because a CI log would not show what drifted; `task generate -- --check`, because it stops at the first failing layer and the flag is easy to forget.

## Consequences

Every generator gets the check from the writer, including future ones. The check is exactly as strict as `generate`: a hand-written file dropped into a generated folder is reported stale, since `generate` would delete it. `tests/test_generate_is_committed.py` asserts `task check` on a clean clone instead of `git status`, so a failure names the file. `.gitattributes` marks `models/**` as `-text`, so no checkout converts line endings and turns every file into drift. The README's first line is the ownership marker: a generated README deleted or its first line edited makes the folder unowned: the check reports a refusal (exit 2) for a folder the declarations still produce, and treats one they no longer produce as hand-written.

## Addendum 2026-11-01

The byte-for-byte check covers owned regions: a region `generate` would rewrite is reported as `changed <file>` with its diff, and a broken region is refused with exit 2 ([ADR-0027](0027-let-a-generator-own-a-marked-region-of-a-hand-written-file.md)).
