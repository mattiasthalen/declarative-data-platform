-- The point-in-time perspective of PR_in_PS_contains, a table macro taking changingTimepoint (ADR-0030).
{{ config(materialized='table_macro', parameters=['changingTimepoint']) }}
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
    {{ anchor_latest({'mnemonic': 'PR_in_PS_contains', 'name': 'PR_in_PS_contains'}, 'changingTimepoint') }}
)
qualify row_number() over (partition by "PR_ID_in" order by "PR_in_PS_contains_ChangedAt" desc) = 1
