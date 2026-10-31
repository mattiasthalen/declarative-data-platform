# declarative-data-platform

Declarations in, a Unified Star Schema out. A source is declared once, as a data contract
and an Anchor model; generators turn the declarations into dbt models, and dbt builds them
into DuckDB:

```
lake (dlt, Parquet)  ->  raw  ->  conform  ->  integrate (Anchor, crt)  ->  serve (USS)
```

| layer | what it is | declared in | written by |
|---|---|---|---|
| ingest | one dlt pipeline per resource, landing each row as JSON in hive-partitioned Parquet | `src/ingest` | `uv run ingest` |
| raw, conform | a view over the lake, and a staged model appending every load, typed by its ODCS v3 contract | `contracts/` | `uv run conform generate` |
| integrate | a concurrent-reliance-temporal Anchor model in Roenbaeck's naming, with its load log, integrity checks and schema tracking | `anchor/model.yaml`, `anchor/mappings/` | `uv run integrate generate` |
| serve | a Puppini Unified Star Schema: staged bridges, dimensions with ghost rows, the bridge | `anchor/model.yaml` | `uv run serve generate` |

## Run it

```sh
uv sync
uv run task ingest                  # land the feed under ./lake (or $LAKE_ROOT)
uv run task generate                # regenerate every layer's models
uv run task build                   # build warehouse/dev.duckdb (TARGET=prod for the other)
```

`uv run task --list` shows every task. Integrate ignores `--full-refresh` and builds incrementally:
its history is only appended to (ADR-0006).

The first business question it answers: how many products were on sale on a given day,
per product line and colour? The sell dates carry the day, so the question reads each
product's current version:

```sql
select product__product_line, product__color, count(*)
from serve__uss.product
where product__valid_to = timestamp '9999-12-31' and _key__product like '%|%'
  and product__sell_start <= date '2013-06-01'
  and (product__sell_end is null or product__sell_end >= date '2013-06-01')
  and (product__discontinued is null or date '2013-06-01' < product__discontinued)
group by all;
```

## Read next

- `CLAUDE.md`: how the work is done here.
- `docs/adr/`: the decisions, in Nygard's format.
- `docs/lexicon.md` and `docs/assumptions.md`.
