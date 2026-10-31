-- Every anchor of every model version.
{{ config(materialized='view') }}
select
    s.version,
    s.activation,
    s.schema->'schema'->'metadata'->>'temporalization' as temporalization,
    a.mnemonic || '_' || (s.schema->'schema'->'anchor'->a.mnemonic->>'descriptor') as name,
    s.schema->'schema'->'anchor'->a.mnemonic->>'descriptor' as descriptor,
    a.mnemonic,
    s.schema->'schema'->'anchor'->a.mnemonic->'metadata'->>'capsule' as capsule,
    s.schema->'schema'->'anchor'->a.mnemonic->>'identity' as identity,
    s.schema->'schema'->'anchor'->a.mnemonic->'metadata'->>'generator' as generator,
    coalesce(json_array_length(s.schema->'schema'->'anchor'->a.mnemonic->'attributes'), 0) as numberOfAttributes,
    s.schema->'schema'->'anchor'->a.mnemonic->>'description' as description
from {{ ref('_Schema') }} s, unnest(json_keys(s.schema->'schema'->'anchor')) as a(mnemonic)
