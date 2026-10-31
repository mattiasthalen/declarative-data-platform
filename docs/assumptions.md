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

## Measured (2026-10-30, the AdventureWorks OData feed)

- The feed pages at 500 rows via `@odata.nextLink`.
- Field names are PascalCase with `Id` (not `ID`): `ProductId`, `ProductSubcategoryId`, `ProductModelId`, `Rowguid`. `json_extract_string` matches names case-sensitively.
- Dates are plain `YYYY-MM-DD` with no time or offset, `ModifiedDate` included (2026-10-31).
- Products: 504 rows; every `ModifiedDate` is 2014-02-08.
- `ProductLine` is padded (`'R '`, `'M '`, `'T '`, `'S '`) or null (225 rows). `Color` is null for 247. `SellEndDate` is null for 402.
