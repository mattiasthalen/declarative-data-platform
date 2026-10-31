-- Every attribute of every model version.
{{ config(materialized='view') }}
select
    s.version,
    s.activation,
    s.schema->'schema'->'metadata'->>'temporalization' as temporalization,
    x.anchor || '_' || x.mnemonic || '_' || (x.a->>'descriptor') || '_' || (x.t->>'descriptor') as name,
    x.t->>'descriptor' as descriptor,
    x.mnemonic,
    x.t->'metadata'->>'capsule' as capsule,
    x.t->>'dataRange' as dataRange,
    (x.t->>'knotRange') is not null as knotted,
    x.t->>'knotRange' as knotRange,
    (x.t->>'timeRange') is not null as historized,
    x.t->>'timeRange' as timeRange,
    x.t->'metadata'->>'generator' as generator,
    x.t->'metadata'->>'assertive' as assertive,
    x.t->'metadata'->>'restatable' as restatable,
    x.t->'metadata'->>'idempotent' as idempotent,
    x.anchor as anchorMnemonic,
    x.a->>'descriptor' as anchorDescriptor,
    x.a->>'identity' as anchorIdentity,
    x.t->>'description' as description,
    coalesce(json_array_length(x.t->'key'), 0) as numberOfKeyStops
from {{ ref('_Schema') }} s,
lateral (
    select
        a.anchor,
        s.schema->'schema'->'anchor'->a.anchor as a,
        t.mnemonic,
        s.schema->'schema'->'anchor'->a.anchor->'attribute'->t.mnemonic as t
    from unnest(json_keys(s.schema->'schema'->'anchor')) as a(anchor),
        unnest(json_keys(s.schema->'schema'->'anchor'->a.anchor->'attribute')) as t(mnemonic)
) x
