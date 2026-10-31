{#- The load log of Anchor batches, on the pattern of Lars Rönnbäck's LOAD_BATCH_LOG (ADR-0007).

    open_batch runs before the first model: it opens a RUNNING batch, whose id every Anchor
    row written by this invocation carries in its Metadata column (anchor_batch).
    close_batch runs after the last node. If no Anchor row carries the batch, it wrote nothing
    and the batch is removed. If serve has not read the batches, because a node errored or was
    skipped or because serve was not selected, every RUNNING batch stays RUNNING, and the
    next invocation opens a new one. Otherwise every RUNNING batch, this one and any an
    earlier build left, closes SUCCEEDED, or VIOLATIONS with the count from IntegrityViolations. -#}

{% macro load_batch_log() -%}
    integrate."LOAD_BATCH_LOG"
{%- endmacro %}

{% macro anchor_batch() -%}
    (select max("BATCH_ID") from {{ load_batch_log() }})
{%- endmacro %}

{% macro open_batch() %}
create schema if not exists integrate;
create table if not exists {{ load_batch_log() }} (
    "BATCH_ID" integer not null primary key,
    "STARTED_AT" timestamp not null,
    "COMPLETED_AT" timestamp,
    "STATUS" varchar(20),
    "INTEGRITY_VIOLATIONS" integer
);
insert into {{ load_batch_log() }} ("BATCH_ID", "STARTED_AT", "STATUS")
select coalesce(max("BATCH_ID"), 0) + 1, cast(now() as timestamp), 'RUNNING'
from {{ load_batch_log() }};
{% endmacro %}

{% macro close_batch(results) %}
    {%- if not execute -%}{{ return('') }}{%- endif -%}
    {%- set metadata_columns = run_query(
        "select c.table_name, c.column_name from information_schema.columns c "
        ~ "join information_schema.tables t on t.table_schema = c.table_schema and t.table_name = c.table_name "
        ~ "where c.table_schema = 'integrate' and t.table_type = 'BASE TABLE' "
        ~ "and c.column_name like 'Metadata\\_%' escape '\\' order by 1, 2"
    ) -%}
    {%- set references = [] -%}
    {%- for row in metadata_columns.rows -%}
        {%- do references.append(
            'select count(*) as n from integrate."' ~ row[0] ~ '" where "' ~ row[1] ~ '" = ' ~ anchor_batch()
        ) -%}
    {%- endfor -%}
    {%- set referenced = 0 -%}
    {%- if references | length > 0 -%}
        {%- set referenced = run_query(
            'select sum(n) from (' ~ (references | join(' union all ')) ~ ')'
        ).columns[0].values()[0] -%}
    {%- endif -%}

    {%- set statements = [] -%}
    {%- if referenced == 0 -%}
        {%- do statements.append('delete from ' ~ load_batch_log() ~ ' where "BATCH_ID" = ' ~ anchor_batch()) -%}
    {%- endif -%}

    {#- Serve rebuilds the identities that RUNNING batches touched, so a batch stays RUNNING
        until serve has read it: when any node errored or was skipped, or when the invocation
        did not build every serve model. A failed test holds it only through the serve models it
        skips; a failing IntegrityViolations skips none, and VIOLATIONS records it. -#}
    {%- set unfinished = results | selectattr('status', 'in', ['error', 'skipped']) | list -%}
    {%- set built = results | selectattr('status', 'equalto', 'success') | map(attribute='node.unique_id') | list -%}
    {%- set unserved = [] -%}
    {%- for node in graph.nodes.values() -%}
        {%- if node.resource_type == 'model' and 'serve' in node.fqn and node.unique_id not in built -%}
            {%- do unserved.append(node.unique_id) -%}
        {%- endif -%}
    {%- endfor -%}
    {%- if unfinished | length > 0 or unserved | length > 0 -%}
        {{ return((statements | join('; ')) or 'select 1') }}
    {%- endif -%}

    {%- set violations = adapter.get_relation(database=target.database, schema='integrate', identifier='IntegrityViolations') -%}
    {%- set counted = 'coalesce((select count(*) from integrate."IntegrityViolations"), 0)' if violations is not none else '0' -%}
    {%- do statements.append(
        'update ' ~ load_batch_log() ~ ' set "COMPLETED_AT" = cast(now() as timestamp), '
        ~ '"INTEGRITY_VIOLATIONS" = ' ~ counted ~ ', '
        ~ '"STATUS" = case when ' ~ counted ~ ' = 0 then \'SUCCEEDED\' else \'VIOLATIONS\' end '
        ~ 'where "STATUS" = \'RUNNING\''
    ) -%}
    {{ return(statements | join('; ')) }}
{% endmacro %}
