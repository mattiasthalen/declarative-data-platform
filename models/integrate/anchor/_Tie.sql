-- Every tie of every model version.
{{ config(materialized='view') }}
select
    s.version,
    s.activation,
    s.schema->'schema'->'metadata'->>'temporalization' as temporalization,
    t.name,
    s.schema->'schema'->'tie'->t.name->'metadata'->>'capsule' as capsule,
    (s.schema->'schema'->'tie'->t.name->>'timeRange') is not null as historized,
    s.schema->'schema'->'tie'->t.name->>'timeRange' as timeRange,
    s.schema->'schema'->'tie'->t.name->>'description' as description
from {{ ref('_Schema') }} s, unnest(json_keys(s.schema->'schema'->'tie')) as t(name)
