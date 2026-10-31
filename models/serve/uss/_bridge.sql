-- The bridge: every staged bridge unioned by name. A key a stage lacks is not applicable.
{{ config(materialized='view') }}
select
    stage,
    coalesce(_key__product, '[not applicable]') as _key__product,
    _valid_from,
    _valid_to
from (
    select * from {{ ref('bridge__product') }}
)
