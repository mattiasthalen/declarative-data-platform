{#- The landed files of one resource under $LAKE_ROOT (ADR-0001): the source row as JSON in
    `data`, dlt's `_dlt_load_id` and `_dlt_id`, the file's name, and the hive folders `date`
    and `hour`. With no file landed yet it is the same columns and no rows, so a build over an
    empty lake succeeds. -#}
{% macro read_lake(resource) -%}
    {%- set pattern = env_var('LAKE_ROOT', 'lake') ~ '/' ~ resource ~ '/date=*/hour=*/*.parquet' -%}
    {%- set landed = 0 -%}
    {%- if execute -%}
        {%- set landed = run_query("select count(*) from glob('" ~ pattern ~ "')").columns[0].values()[0] -%}
    {%- endif -%}
    {%- if landed > 0 %}
select
    cast(data as varchar) as data,
    cast(_dlt_load_id as varchar) as _dlt_load_id,
    cast(_dlt_id as varchar) as _dlt_id,
    filename,
    cast("date" as date) as "date",
    cast("hour" as integer) as "hour"
from read_parquet('{{ pattern }}', hive_partitioning = true, filename = true, union_by_name = true)
    {%- else %}
select
    cast(null as varchar) as data,
    cast(null as varchar) as _dlt_load_id,
    cast(null as varchar) as _dlt_id,
    cast(null as varchar) as filename,
    cast(null as date) as "date",
    cast(null as integer) as "hour"
where false
    {%- endif %}
{%- endmacro %}
