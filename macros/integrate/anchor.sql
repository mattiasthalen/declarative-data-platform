{#- The load of a concurrent-reliance-temporal (crt) Anchor model in set-based SQL (ADR-0006).

    Anchor's own generators enforce the loading rules with triggers on the latest views.
    DuckDB has no triggers, so the generated integrate models call these macros instead.
    Every macro takes `a`, a dict the integrate generator writes into each model: the
    anchor's and attribute's names in Roenbaeck's default naming, their types, and where
    the attribute is loaded from.

    The rules, per attribute and identity, applying the pending loads oldest first:
    - the same value at a held ChangedAt: nothing (idempotent);
    - the same value as the version before, at a later ChangedAt: a restatement, skipped;
    - another value at a held ChangedAt: a correction, the held posit retracted (reliability 0)
      and the new value asserted, both at the new PositedAt;
    - a new value: a posit and an annex at reliability 1;
    - a null from the source: a retraction of the version in effect, unless the latest
      statement about that time is already a retraction;
    - a value whose cast failed in conform, or an identity missing from a load: nothing.
    Two different values for one version at one PositedAt are a contradiction: the build fails. -#}


{#- The relation in integrate, or none before its first build. Read this way, and not through
    ref(), where a ref would close a cycle: the posit model reads its own annex, and the anchor
    and identifier models read the identifier's tables. -#}
{% macro anchor_relation(identifier) -%}
    {{ return(adapter.get_relation(database=target.database, schema='integrate', identifier=identifier)) }}
{%- endmacro %}


{#- The natural key of every identity, from the latest asserted identifier values. -#}
{% macro anchor_key_select(a, posit, annex) -%}
    {%- set m = a.identifier_mnemonic -%}
    select
        p."{{ m }}_{{ a.anchor_mnemonic }}_ID" as "{{ a.anchor_mnemonic }}_ID",
        p."{{ a.identifier_value }}"
    from {{ posit }} p
    join (
        select "{{ m }}_ID", arg_max("{{ m }}_Reliability", "{{ m }}_PositedAt") as reliability
        from {{ annex }}
        where "{{ m }}_Positor" = 0
        group by "{{ m }}_ID"
    ) latest on latest."{{ m }}_ID" = p."{{ m }}_ID"
    where latest.reliability >= 1
    qualify row_number() over (
        partition by p."{{ m }}_{{ a.anchor_mnemonic }}_ID" order by p."{{ m }}_ChangedAt" desc
    ) = 1
{%- endmacro %}


{#- Natural key -> identity, for the anchor and its identifier attribute. A key the key view
    knows keeps its identity. Keys it does not know are numbered by first appearance and
    matched, in order, to identities the anchor holds that no key has claimed yet; the anchor
    model adds identities until there are enough. A build that fails between the anchor and
    the identifier therefore leaves identities the next build claims in the same order. -#}
{% macro anchor_identities(a) -%}
    {%- set posit = anchor_relation(a.identifier_posit) -%}
    {%- set annex = anchor_relation(a.identifier_annex) -%}
    {%- set anchor = anchor_relation(a.anchor) -%}
    {%- set id = a.anchor_mnemonic ~ '_ID' -%}
known_keys as (
    {%- if posit is not none and annex is not none %}
    {{ anchor_key_select(a, posit, annex) }}
    {%- else %}
    select cast(null as {{ a.identity_type }}) as "{{ id }}", cast(null as varchar) as "{{ a.identifier_value }}"
    where false
    {%- endif %}
),

unknown_keys as (
    select
        s."{{ a.key_column }}" as natural_key,
        row_number() over (
            order by min(s._dlt__extracted_at), min(cast(s._dlt__load_id as decimal(38, 9))), s."{{ a.key_column }}"
        ) as claim
    from {{ ref(a.source) }} s
    where s."{{ a.key_column }}" is not null
      and s."{{ a.changed_at }}" is not null
      and s."{{ a.key_column }}" not in (select "{{ a.identifier_value }}" from known_keys)
    group by s."{{ a.key_column }}"
),

unclaimed_identities as (
    {%- if anchor is not none %}
    select "{{ id }}", row_number() over (order by "{{ id }}") as claim
    from {{ anchor }}
    where "{{ id }}" not in (select "{{ id }}" from known_keys)
    {%- else %}
    select cast(null as {{ a.identity_type }}) as "{{ id }}", cast(null as bigint) as claim
    where false
    {%- endif %}
),

identities as (
    select "{{ a.identifier_value }}" as natural_key, "{{ id }}" as id from known_keys
    union all
    select k.natural_key, u."{{ id }}" from unknown_keys k join unclaimed_identities u on u.claim = k.claim
)
{%- endmacro %}


{#- The anchor: one new identity for every natural key that has none yet. -#}
{% macro anchor_anchor(a) -%}
    {%- set id = a.anchor_mnemonic ~ '_ID' -%}
with {{ anchor_identities(a) }}

select
    cast(
        {%- if is_incremental() %} (select coalesce(max("{{ id }}"), 0) from {{ this }}){% else %} 0{% endif %}
        + row_number() over (order by k.claim) as {{ a.identity_type }}
    ) as "{{ id }}",
    cast({{ anchor_batch() }} as integer) as "Metadata_{{ a.anchor_mnemonic }}"
from unknown_keys k
where k.claim > (select count(*) from unclaimed_identities)
{%- endmacro %}


{#- What the pending loads assert and retract for one attribute: the CTEs ending in `actions`
    (identity, ChangedAt, value, reliability, PositedAt). The posit and annex models both call
    it; it reads only the annex as it stood before this build, so both see the same actions. -#}
{% macro anchor_actions(a) -%}
    {%- set m = a.mnemonic -%}
    {%- set posit = anchor_relation(a.posit) -%}
    {%- set annex = anchor_relation(a.annex) -%}
    {%- set held = posit is not none and annex is not none -%}
    {%- set state_type = 'struct(changed_at ' ~ a.time_type ~ ', value ' ~ a.value_type ~ ', reliability tinyint)' -%}
    {%- set action_type = 'struct(changed_at ' ~ a.time_type ~ ', value ' ~ a.value_type ~ ', reliability tinyint, positing_at timestamp)' -%}
{% if a.is_identifier %}{{ anchor_identities(a) }},{% else %}identities as (
    select "{{ a.identifier_value }}" as natural_key, "{{ a.anchor_mnemonic }}_ID" as id
    from {{ ref(a.key_view) }}
),{% endif %}

-- The rows of every load at or after the newest PositedAt this attribute holds, less those that
-- repeat the key's row in the load before: an unchanged load adds no step to the recursion,
-- though every build still reads the whole conform history once per attribute. Only a key's
-- lone row in a load is compared, with a lone row in the load before, so two rows that
-- contradict each other in one load always reach the contradiction check. A load at the
-- newest PositedAt is applied again, which changes nothing: the rules are idempotent.
source_rows as (
    select natural_key, value, changed_at, positing_at, load_number, cast_failed
    from (
        select
            *,
            rows_in_load = 1
                and lag(rows_in_load) over by_load = 1
                and {'value': value, 'changed_at': changed_at, 'cast_failed': cast_failed}
                    is not distinct from lag({'value': value, 'changed_at': changed_at, 'cast_failed': cast_failed}) over by_load
                as repeats
        from (
            select *, count(*) over (partition by natural_key, load_number) as rows_in_load
            from (
                select
                    s."{{ a.key_column }}" as natural_key,
                    cast(s."{{ a.column }}" as {{ a.value_type }}) as value,
                    cast(s."{{ a.changed_at }}" as {{ a.time_type }}) as changed_at,
                    s._dlt__extracted_at as positing_at,
                    cast(s._dlt__load_id as decimal(38, 9)) as load_number,
                    list_contains(s._contract__cast_failed, '{{ a.column }}') as cast_failed
                from {{ ref(a.source) }} s
                where s."{{ a.key_column }}" is not null
                  and s."{{ a.changed_at }}" is not null
            )
        )
        window by_load as (partition by natural_key order by positing_at, load_number, changed_at)
    )
    where not coalesce(repeats, false)
    {%- if held %}
      and positing_at >= coalesce(
          (select max("{{ m }}_PositedAt") from {{ annex }}), cast('0001-01-01' as timestamp)
      )
    {%- endif %}
),

incoming as (
    select
        i.id,
        r.value,
        r.changed_at,
        r.positing_at,
        r.cast_failed,
        row_number() over (
            partition by i.id order by r.positing_at, r.load_number, r.changed_at, r.value nulls first
        ) as step
    from source_rows r
    join identities i on i.natural_key = r.natural_key
),

-- Two different values for one version at one PositedAt cannot both be asserted.
contradictions as (
    select id, changed_at, positing_at
    from incoming
    where not cast_failed
    group by id, changed_at, positing_at
    having count(distinct coalesce(cast(value as varchar), chr(0))) > 1
),

checked as (
    select *
    from incoming
    where case
        when (select count(*) from contradictions) > 0
        then error('{{ a.name }}: two different values for one version at one PositedAt')
        else true
    end
),

-- What the attribute holds for the identities that have pending loads: every posit with an
-- annex, and the reliability of its latest annex row.
held as (
    {%- if held %}
    select
        p."{{ m }}_{{ a.anchor_mnemonic }}_ID" as id,
        p."{{ m }}_ChangedAt" as changed_at,
        p."{{ a.name }}" as value,
        arg_max(x."{{ m }}_Reliability", x."{{ m }}_PositedAt") as reliability
    from {{ posit }} p
    join {{ annex }} x on x."{{ m }}_ID" = p."{{ m }}_ID"
    where x."{{ m }}_Positor" = 0
      and p."{{ m }}_{{ a.anchor_mnemonic }}_ID" in (select id from checked)
    group by all
    {%- else %}
    select
        cast(null as {{ a.identity_type }}) as id,
        cast(null as {{ a.time_type }}) as changed_at,
        cast(null as {{ a.value_type }}) as value,
        cast(null as tinyint) as reliability
    where false
    {%- endif %}
),

held_lists as (
    select id, list({'changed_at': changed_at, 'value': value, 'reliability': reliability}) as state
    from held
    group by id
),

-- Apply each identity's pending rows one at a time, carrying what it holds as a list.
steps(id, step, state, acts) as (
    select
        ids.id,
        0,
        coalesce(h.state, []::{{ state_type }}[]),
        []::{{ action_type }}[]
    from (select distinct id from checked) ids
    left join held_lists h on h.id = ids.id

    union all

    select s.id, s.step + 1, d.state, d.acts
    from steps s
    join checked i on i.id = s.id and i.step = s.step + 1
    cross join lateral (
        select
            case
                when i.cast_failed then s.state
                when i.value is null then list_transform(s.state, lambda x:
                    case when x.changed_at = z.retract_at and x.reliability = 1
                        then {'changed_at': x.changed_at, 'value': x.value, 'reliability': 0::tinyint}
                        else x end)
                else list_concat(
                    list_transform(s.state, lambda x: case
                        when x.changed_at = i.changed_at and x.reliability = 1 and x.value <> i.value
                            then {'changed_at': x.changed_at, 'value': x.value, 'reliability': 0::tinyint}
                        when z.asserts and x.changed_at = i.changed_at and x.value = i.value
                            then {'changed_at': x.changed_at, 'value': x.value, 'reliability': 1::tinyint}
                        else x end),
                    case when z.asserts and not z.posited
                        then [{'changed_at': i.changed_at, 'value': i.value, 'reliability': 1::tinyint}]
                        else []::{{ state_type }}[] end)
            end as state,
            case
                when i.cast_failed then []::{{ action_type }}[]
                when i.value is null then list_transform(
                    list_filter(s.state, lambda x: x.changed_at = z.retract_at and x.reliability = 1),
                    lambda x: {'changed_at': x.changed_at, 'value': x.value, 'reliability': 0::tinyint, 'positing_at': i.positing_at})
                else list_concat(
                    list_transform(
                        list_filter(s.state, lambda x: x.changed_at = i.changed_at and x.reliability = 1 and x.value <> i.value),
                        lambda x: {'changed_at': x.changed_at, 'value': x.value, 'reliability': 0::tinyint, 'positing_at': i.positing_at}),
                    case when z.asserts
                        then [{'changed_at': i.changed_at, 'value': i.value, 'reliability': 1::tinyint, 'positing_at': i.positing_at}]
                        else []::{{ action_type }}[] end)
            end as acts
        from (
            select
                -- a null retracts the version in effect at its ChangedAt, unless the latest
                -- statement about that time already retracted it
                list_max(list_transform(
                    list_filter(s.state, lambda x: x.changed_at <= i.changed_at), lambda x: x.changed_at
                )) as retract_at,
                -- a value is asserted unless it is held already, or restates the version before
                not coalesce(list_bool_or(list_transform(s.state, lambda x:
                        x.changed_at = i.changed_at and x.reliability = 1 and x.value = i.value)), false)
                    and coalesce(
                        list_last(list_sort(list_transform(
                            list_filter(s.state, lambda x: x.changed_at < i.changed_at and x.reliability = 1),
                            lambda x: {'changed_at': x.changed_at, 'value': x.value}
                        ))).value is distinct from i.value,
                        true
                    ) as asserts,
                coalesce(list_bool_or(list_transform(s.state, lambda x:
                    x.changed_at = i.changed_at and x.value = i.value)), false) as posited
        ) z
    ) d
),

actions as (
    select
        s.id,
        t.act.changed_at,
        t.act.value,
        t.act.reliability,
        t.act.positing_at
    from steps s, unnest(s.acts) as t(act)
)
{%- endmacro %}


{#- The posit table: a row for every value asserted that it does not hold yet. -#}
{% macro anchor_posit(a) -%}
    {%- set m = a.mnemonic -%}
with recursive {{ anchor_actions(a) }},

new_posits as (
    select distinct id, changed_at, value
    from actions
    where reliability = 1
    {%- if is_incremental() %}
      and not exists (
        select 1 from {{ this }} p
        where p."{{ m }}_{{ a.anchor_mnemonic }}_ID" = actions.id
          and p."{{ m }}_ChangedAt" = actions.changed_at
          and p."{{ a.name }}" = actions.value
      )
    {%- endif %}
)

select
    cast(
        {%- if is_incremental() %} (select coalesce(max("{{ m }}_ID"), 0) from {{ this }}){% else %} 0{% endif %}
        + row_number() over (order by id, changed_at, value) as {{ a.identity_type }}
    ) as "{{ m }}_ID",
    cast(id as {{ a.identity_type }}) as "{{ m }}_{{ a.anchor_mnemonic }}_ID",
    cast(value as {{ a.value_type }}) as "{{ a.name }}",
    cast(changed_at as {{ a.time_type }}) as "{{ m }}_ChangedAt"
from new_posits
{%- endmacro %}


{#- The annex table: an assertion or retraction for every action, stamped with the batch. -#}
{% macro anchor_annex(a) -%}
    {%- set m = a.mnemonic -%}
with recursive {{ anchor_actions(a) }}

select
    p."{{ m }}_ID",
    cast(actions.positing_at as timestamp) as "{{ m }}_PositedAt",
    cast(0 as tinyint) as "{{ m }}_Positor",
    cast(actions.reliability as tinyint) as "{{ m }}_Reliability",
    cast({{ anchor_batch() }} as integer) as "Metadata_{{ m }}"
from actions
join {{ ref(a.posit) }} p
  on p."{{ m }}_{{ a.anchor_mnemonic }}_ID" = actions.id
 and p."{{ m }}_ChangedAt" = actions.changed_at
 and p."{{ a.name }}" = actions.value
{%- endmacro %}


{#- The assembled view of one attribute: every annex row with its posit. -#}
{% macro anchor_assembled(a) -%}
    {%- set m = a.mnemonic -%}
select
    x."Metadata_{{ m }}",
    p."{{ m }}_ID",
    x."{{ m }}_PositedAt",
    x."{{ m }}_Positor",
    x."{{ m }}_Reliability",
    cast(x."{{ m }}_Reliability" >= 1 as tinyint) as "{{ m }}_Reliable",
    p."{{ m }}_{{ a.anchor_mnemonic }}_ID",
    p."{{ a.name }}",
    p."{{ m }}_ChangedAt"
from {{ ref(a.posit) }} p
join {{ ref(a.annex) }} x on x."{{ m }}_ID" = p."{{ m }}_ID"
{%- endmacro %}


{#- The latest version of one attribute per identity: of positor 0's latest annex row for each
    posit, the reliable ones, and of those the latest ChangedAt. With `changed_by`, a SQL expression
    such as the point-in-time perspective's parameter, only posits that changed at or before it
    count, so nothing shows before the attribute's first ChangedAt (ADR-0030). -#}
{% macro anchor_latest(a, changed_by=none) -%}
    {%- set m = a.mnemonic -%}
select *
from {{ ref(a.name) }}
where "{{ m }}_Positor" = 0
{%- if changed_by %}
  and "{{ m }}_ChangedAt" <= {{ changed_by }}
{%- endif %}
qualify row_number() over (partition by "{{ m }}_ID" order by "{{ m }}_PositedAt" desc) = 1
    and "{{ m }}_Reliable" = 1
{%- endmacro %}

