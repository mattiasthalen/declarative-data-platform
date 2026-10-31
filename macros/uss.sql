{#- The Unified Star Schema over an anchor, on business time (ADR-0011). Each macro takes `e`,
    the dict the serve generator writes: the entity, its anchor, and each attribute with the
    dimension column it fills. -#}


{#- The identities whose rows a batch not yet closed has written: this build's, and those a
    failed build left RUNNING. Only their versions are rebuilt. -#}
{% macro uss_affected(e) -%}
    {%- set running = 'select "BATCH_ID" from ' ~ load_batch_log() ~ ' where "STATUS" = \'RUNNING\'' -%}
    select "{{ e.anchor_mnemonic }}_ID" as id
    from {{ ref(e.anchor) }}
    where "Metadata_{{ e.anchor_mnemonic }}" in ({{ running }})
    {%- for t in e.attributes %}
    union
    select "{{ t.prefix }}_{{ e.anchor_mnemonic }}_ID"
    from {{ ref(t.name) }}
    where "Metadata_{{ t.prefix }}" in ({{ running }})
    {%- endfor %}
{%- endmacro %}


{#- Before an incremental build: remove the versions of the affected identities, which the
    build then writes again. Ghost rows carry no identity and stay. -#}
{% macro uss_forget(e) -%}
    {%- if is_incremental() -%}
delete from {{ this }}
where split_part(_key__{{ e.entity }}, '|', 1) in (
    select cast(id as varchar) from ({{ uss_affected(e) }})
)
    {%- endif -%}
{%- endmacro %}


{#- The CTEs ending in `versions` (id, valid_from, valid_to, _key): one row per version of each
    identity, from an opening version at 0001-01-01 to each change of any attribute, as positor 0
    states it now. Per attribute a CTE named for its prefix holds the reliable posits (id,
    changed_at, value) to ASOF-join on. -#}
{% macro uss_versions(e) -%}
identities as (
    select "{{ e.anchor_mnemonic }}_ID" as id
    from {{ ref(e.anchor) }}
    {%- if is_incremental() %}
    where "{{ e.anchor_mnemonic }}_ID" in ({{ uss_affected(e) }})
    {%- endif %}
),
{%- for t in e.attributes %}

{{ t.prefix | lower }} as (
    select
        "{{ t.prefix }}_{{ e.anchor_mnemonic }}_ID" as id,
        "{{ t.prefix }}_ChangedAt" as changed_at,
        "{{ t.name }}" as value
    from {{ ref(t.name) }}
    where "{{ t.prefix }}_Positor" = 0
      and "{{ t.prefix }}_{{ e.anchor_mnemonic }}_ID" in (select id from identities)
    qualify row_number() over (partition by "{{ t.prefix }}_ID" order by "{{ t.prefix }}_PositedAt" desc) = 1
        and "{{ t.prefix }}_Reliable" = 1
),
{%- endfor %}

boundaries as (
    select id, cast('0001-01-01' as timestamp) as valid_from from identities
    {%- for t in e.attributes %}
    union
    select id, cast(changed_at as timestamp) from {{ t.prefix | lower }}
    {%- endfor %}
),

versions as (
    select
        id,
        valid_from,
        lead(valid_from, 1, cast('9999-12-31' as timestamp)) over (partition by id order by valid_from) as valid_to,
        cast(id as varchar) || '|' || cast(valid_from as varchar) as _key
    from boundaries
)
{%- endmacro %}
