---
paths:
  - "**/ingest/**"
---

# Ingest rules

- **One dlt pipeline per resource**, named `<source>__<resource>`, so one faulty resource never
  halts the rest ([ADR-0001](../../docs/adr/0001-land-each-source-row-as-json-in-hive-partitioned-parquet.md)).
- **Land the row as it came.** The source row is one JSON field beside dlt's meta fields, in
  hive-partitioned Parquet under `LAKE_ROOT`. Nothing is renamed or typed here: that is the
  contract's job ([ADR-0001](../../docs/adr/0001-land-each-source-row-as-json-in-hive-partitioned-parquet.md)).
