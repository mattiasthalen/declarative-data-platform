# Architecture decision records

Nygard's format: Context, Decision, Consequences, with a Status. One decision per record.

| ADR | Decision | Status |
|---|---|---|
| [0001](0001-land-each-source-row-as-json-in-hive-partitioned-parquet.md) | Land each source row as JSON in hive-partitioned Parquet, one dlt pipeline per resource | Accepted (2026-10-31) |
| [0002](0002-name-conformed-columns-in-snake-case-with-dlt-platform-columns.md) | Name conformed columns in snake_case, and group platform columns under `_dlt__` | Accepted (2026-10-31) |
| [0003](0003-keep-anchor-modeling-default-naming-verbatim.md) | Keep Anchor Modeling's default naming verbatim in integrate | Accepted (2026-10-31) |
| [0004](0004-declare-the-anchor-model-as-one-yaml-mirror-of-anchor-xsd.md) | Declare the Anchor model as one YAML file that mirrors anchor.xsd | Accepted (2026-10-31) |
| [0005](0005-identify-anchors-by-surrogate-found-through-the-key-view.md) | Identify anchors by a surrogate found through the key view | Accepted (2026-10-31) |
| [0006](0006-apply-anchor-crt-loading-rules-in-generated-sql.md) | Apply Anchor's crt loading rules in generated SQL: decisive, idempotent, not assertive | Accepted (2026-10-31) |
| [0007](0007-number-loads-with-a-batch-log-in-anchor-metadata.md) | Number loads with a batch log and stamp the batch in Anchor's Metadata columns | Accepted (2026-10-31) |
| [0008](0008-track-the-anchor-model-in-the-database.md) | Track the Anchor model in the database with Anchor's schema tables | Accepted (2026-10-31) |
| [0009](0009-stage-conform-by-appending-whole-loads.md) | Stage conform by appending every newer load whole, and let Anchor discard repeats | Accepted (2026-10-31) |
| [0010](0010-cast-with-try-cast-and-never-let-a-failed-cast-retract.md) | Cast with try_cast, and never let a failed cast retract | Accepted (2026-10-31) |
| [0011](0011-serve-a-uss-from-staged-bridges-unioned-by-name.md) | Serve a Unified Star Schema from incremental staged bridges unioned by name | Accepted (2026-10-31) |
| [0012](0012-lay-the-repo-out-by-kind-with-generator-owned-folders.md) | Lay the repo out by kind, and let a generator own only folders that carry its README | Accepted (2026-10-31); partly superseded by ADR-0015 |
| [0013](0013-check-generated-output-byte-for-byte-through-the-writer-that-owns-it.md) | Check generated output byte for byte through the writer that owns it | Accepted (2026-10-31) |
| [0014](0014-require-ci-check-and-test-jobs-to-pass-before-merging-into-main.md) | Require CI's check and test jobs to pass before anything merges into main | Accepted (2026-10-31) |
| [0015](0015-keep-each-layers-files-in-layer-named-folders-and-scope-agent-rules-to-them.md) | Keep each layer's files in folders named after the layer, and scope agent rules to them | Accepted (2026-10-31) |
