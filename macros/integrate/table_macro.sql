{#- A model as a DuckDB table macro: `create or replace macro <model>(<parameters>) as table <select>`,
    for Anchor's perspectives that take a time (ADR-0030). The select names each parameter as a
    column; DuckDB binds it on creation, so its relations must exist, and expands it where it is
    called, against the relations as they are then (A24). A macro is not a relation, so dbt is handed none. -#}
{% materialization table_macro, adapter='duckdb' %}
    {%- set parameters = config.require('parameters') -%}
    {{ run_hooks(pre_hooks) }}
    {% call statement('main') -%}
        create or replace macro {{ this }}({{ parameters | join(', ') }}) as table
        {{ sql }}
    {%- endcall %}
    {{ run_hooks(post_hooks) }}
    {% do adapter.commit() %}
    {{ return({'relations': []}) }}
{% endmaterialization %}
