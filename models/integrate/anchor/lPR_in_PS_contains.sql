-- The latest perspective of PR_in_PS_contains: per Product, its latest reliable ProductSubcategory as positor 0 states it now.
{{ config(materialized='view') }}
select
    "Metadata_PR_in_PS_contains",
    "PR_in_PS_contains_ID",
    "PR_in_PS_contains_ChangedAt",
    "PR_in_PS_contains_PositedAt",
    "PR_in_PS_contains_Positor",
    "PR_in_PS_contains_Reliability",
    "PR_ID_in",
    "PS_ID_contains"
from (
    {{ anchor_latest({'mnemonic': 'PR_in_PS_contains', 'name': 'PR_in_PS_contains'}) }}
)
qualify row_number() over (partition by "PR_ID_in" order by "PR_in_PS_contains_ChangedAt" desc) = 1
