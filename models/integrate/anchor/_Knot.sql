-- Every knot of every model version.
{{ config(materialized='view') }}
select
    s.version,
    s.activation,
    s.schema->'schema'->'metadata'->>'temporalization' as temporalization,
    k.mnemonic || '_' || (s.schema->'schema'->'knot'->k.mnemonic->>'descriptor') as name,
    s.schema->'schema'->'knot'->k.mnemonic->>'descriptor' as descriptor,
    k.mnemonic,
    s.schema->'schema'->'knot'->k.mnemonic->'metadata'->>'capsule' as capsule,
    s.schema->'schema'->'knot'->k.mnemonic->>'dataRange' as dataRange,
    s.schema->'schema'->'knot'->k.mnemonic->>'identity' as identity,
    s.schema->'schema'->'knot'->k.mnemonic->>'description' as description
from {{ ref('_Schema') }} s, unnest(json_keys(s.schema->'schema'->'knot')) as k(mnemonic)
