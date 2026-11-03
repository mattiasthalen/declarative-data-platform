-- The time-traveling perspective of PR_in_PS_contains, a table macro taking changingTimepoint and positingTimepoint (ADR-0033).
{{ config(materialized='table_macro', parameters=['changingTimepoint', 'positingTimepoint']) }}
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
    {{ anchor_latest({'mnemonic': 'PR_in_PS_contains', 'name': 'PR_in_PS_contains'}, 'changingTimepoint', posited_by='positingTimepoint') }}
)
qualify row_number() over (partition by "PR_ID_in" order by "PR_in_PS_contains_ChangedAt" desc) = 1
