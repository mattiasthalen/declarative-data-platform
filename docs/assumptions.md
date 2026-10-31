# Assumptions

What the design still assumes, and how you would know it stopped holding; then facts measured against live data.

## Standing

| id | assumption | area | how you would know it stopped holding |
|---|---|---|---|
| A1 | A full pull of Products is small enough to repeat every run. | ingest | A Products load takes more than a minute or the lake grows past a few hundred MB. |
| A2 | `ModifiedDate` moves whenever a Product value changes in the source. | integrate | A load holds a different value for a product with an unchanged `ModifiedDate` more often than rarely: corrections pile up in the annexes. |
| A3 | dlt's load id is epoch seconds as text, increasing with time. | conform | `try_cast` of `_dlt_load_id` to a number fails, or a later load has a smaller id. |
| A4 | Only one `dbt build` runs against a target at a time. | operations | The orchestrator (story 16) schedules overlapping runs. |
| A5 | DuckDB enforces the primary and unique keys that dbt contracts declare on incremental models. | integrate | A duplicate key is inserted without an error. |

## Measured (2026-10-30, the AdventureWorks OData feed)

- The feed pages at 500 rows via `@odata.nextLink`.
- Products: 504 rows; every `ModifiedDate` is 2014-02-08.
- `ProductLine` is padded (`'R '`, `'M '`, `'T '`, `'S '`) or null (225 rows). `Color` is null for 247. `SellEndDate` is null for 402.
