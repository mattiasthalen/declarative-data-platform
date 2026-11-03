-- The time-traveling perspective of PS_ProductSubcategory, a table macro taking changingTimepoint and positingTimepoint: per identity, each attribute's latest reliable value as positor 0 had stated it by positingTimepoint, of those that changed at or before changingTimepoint (ADR-0033).
{{ config(materialized='table_macro', parameters=['changingTimepoint', 'positingTimepoint']) }}
select
    p."PS_ID",
    p."Metadata_PS",
    sid."Metadata_PS_SID",
    sid."PS_SID_PS_ID",
    sid."PS_SID_ID",
    sid."PS_SID_ChangedAt",
    sid."PS_SID_PositedAt",
    sid."PS_SID_Positor",
    sid."PS_SID_Reliability",
    sid."PS_SID_ProductSubcategory_SourceId",
    nam."Metadata_PS_NAM",
    nam."PS_NAM_PS_ID",
    nam."PS_NAM_ID",
    nam."PS_NAM_ChangedAt",
    nam."PS_NAM_PositedAt",
    nam."PS_NAM_Positor",
    nam."PS_NAM_Reliability",
    nam."PS_NAM_ProductSubcategory_Name"
from {{ ref('PS_ProductSubcategory') }} p
left join (
    select * from (
        {{ anchor_latest({'mnemonic': 'PS_SID', 'name': 'PS_SID_ProductSubcategory_SourceId'}, 'changingTimepoint', posited_by='positingTimepoint') }}
    )
    qualify row_number() over (partition by "PS_SID_PS_ID" order by "PS_SID_ChangedAt" desc) = 1
) sid on sid."PS_SID_PS_ID" = p."PS_ID"
left join (
    select * from (
        {{ anchor_latest({'mnemonic': 'PS_NAM', 'name': 'PS_NAM_ProductSubcategory_Name'}, 'changingTimepoint', posited_by='positingTimepoint') }}
    )
    qualify row_number() over (partition by "PS_NAM_PS_ID" order by "PS_NAM_ChangedAt" desc) = 1
) nam on nam."PS_NAM_PS_ID" = p."PS_ID"
