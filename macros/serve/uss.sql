{#- The Unified Star Schema over an anchor, on business time (ADR-0011). Each macro takes `e`,
    the dict the serve generator writes: the entity, its anchor, and each attribute. -#}


{#- The identities whose rows a batch not yet closed has written: this build's, and those a
    failed build left RUNNING, in its attributes or its ties, and those tied to an identity affected
    in the entity a tie reaches. Only their versions are rebuilt. -#}
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
    {%- for t in e.ties %}
    union
    select "{{ t.identity_column }}"
    from {{ ref(t.name) }}
    where "Metadata_{{ t.name }}" in ({{ running }})
    union
    select "{{ t.identity_column }}"
    from {{ ref(t.name) }}
    where "{{ t.value_column }}" in ({{ uss_affected(t.reaches) }})
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
    identity, a new one at each change of any attribute, as positor 0 states it now. Per attribute
    a CTE named for its prefix holds the reliable posits (id, changed_at, value) to ASOF-join on,
    its earliest posit moved back to 0001-01-01: the first value seen is taken to have held since
    the beginning, so no version is all null (ADR-0011). -#}
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
        case
            when row_number() over (
                partition by "{{ t.prefix }}_{{ e.anchor_mnemonic }}_ID" order by "{{ t.prefix }}_ChangedAt"
            ) = 1 then cast('0001-01-01' as timestamp)
            else cast("{{ t.prefix }}_ChangedAt" as timestamp)
        end as changed_at,
        "{{ t.name }}" as value
    from ({{ anchor_latest({'mnemonic': t.prefix, 'name': t.name}) }})
    where "{{ t.prefix }}_{{ e.anchor_mnemonic }}_ID" in (select id from identities)
),
{%- endfor %}

boundaries as (
    {%- for t in e.attributes %}
    {% if not loop.first %}union
    {% endif %}select id, changed_at as valid_from from {{ t.prefix | lower }}
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


{#- One followed tie `t` of a staged bridge (ADR-0038): per identity, each version of the tie as
    positor 0 states it now, its first held since 0001-01-01 (ADR-0039), intersected with the rows of
    the reached entity's staged bridge. Returns (id, valid_from, _key__<reached>, and the keys that
    stage inherits), one row per interval, for an ASOF join on valid_from. Needs the `identities` CTE
    of `uss_versions`. -#}
{% macro uss_reach(t, reached, keys) -%}
    with versions_of_tie as (
        select
            "{{ t.identity_column }}" as id,
            case
                when row_number() over (partition by "{{ t.identity_column }}" order by "{{ t.name }}_ChangedAt") = 1
                then cast('0001-01-01' as timestamp)
                else cast("{{ t.name }}_ChangedAt" as timestamp)
            end as valid_from,
            "{{ t.value_column }}" as other
        from ({{ anchor_latest({'mnemonic': t.name, 'name': t.name}) }})
        where "{{ t.identity_column }}" in (select id from identities)
    ),
    spans_of_tie as (
        select
            id,
            valid_from,
            lead(valid_from, 1, cast('9999-12-31' as timestamp)) over (partition by id order by valid_from) as valid_to,
            other
        from versions_of_tie
    )
    select
        t.id,
        greatest(t.valid_from, s._valid_from) as valid_from
        {%- for key in keys %},
        s._key__{{ key }}
        {%- endfor %}
    from spans_of_tie t
    join {{ ref('bridge__' ~ reached) }} s
      on split_part(s._key__{{ reached }}, '|', 1) = cast(t.other as varchar)
     and s._valid_from < t.valid_to
     and t.valid_from < s._valid_to
{%- endmacro %}
