-- The point-in-time perspective of PR_Product, a table macro taking changingTimepoint: per identity, each attribute's latest reliable value as positor 0 states it, of those that changed at or before changingTimepoint; nothing before an attribute's first ChangedAt (ADR-0030).
{{ config(materialized='table_macro', parameters=['changingTimepoint']) }}
select
    p."PR_ID",
    p."Metadata_PR",
    num."Metadata_PR_NUM",
    num."PR_NUM_PR_ID",
    num."PR_NUM_ID",
    num."PR_NUM_ChangedAt",
    num."PR_NUM_PositedAt",
    num."PR_NUM_Positor",
    num."PR_NUM_Reliability",
    num."PR_NUM_Product_ProductNumber",
    nam."Metadata_PR_NAM",
    nam."PR_NAM_PR_ID",
    nam."PR_NAM_ID",
    nam."PR_NAM_ChangedAt",
    nam."PR_NAM_PositedAt",
    nam."PR_NAM_Positor",
    nam."PR_NAM_Reliability",
    nam."PR_NAM_Product_Name",
    lin."Metadata_PR_LIN",
    lin."PR_LIN_PR_ID",
    lin."PR_LIN_ID",
    lin."PR_LIN_ChangedAt",
    lin."PR_LIN_PositedAt",
    lin."PR_LIN_Positor",
    lin."PR_LIN_Reliability",
    lin."PR_LIN_Product_ProductLine",
    col."Metadata_PR_COL",
    col."PR_COL_PR_ID",
    col."PR_COL_ID",
    col."PR_COL_ChangedAt",
    col."PR_COL_PositedAt",
    col."PR_COL_Positor",
    col."PR_COL_Reliability",
    col."PR_COL_Product_Color",
    sst."Metadata_PR_SST",
    sst."PR_SST_PR_ID",
    sst."PR_SST_ID",
    sst."PR_SST_ChangedAt",
    sst."PR_SST_PositedAt",
    sst."PR_SST_Positor",
    sst."PR_SST_Reliability",
    sst."PR_SST_Product_SellStart",
    sen."Metadata_PR_SEN",
    sen."PR_SEN_PR_ID",
    sen."PR_SEN_ID",
    sen."PR_SEN_ChangedAt",
    sen."PR_SEN_PositedAt",
    sen."PR_SEN_Positor",
    sen."PR_SEN_Reliability",
    sen."PR_SEN_Product_SellEnd",
    dis."Metadata_PR_DIS",
    dis."PR_DIS_PR_ID",
    dis."PR_DIS_ID",
    dis."PR_DIS_ChangedAt",
    dis."PR_DIS_PositedAt",
    dis."PR_DIS_Positor",
    dis."PR_DIS_Reliability",
    dis."PR_DIS_Product_Discontinued"
from {{ ref('PR_Product') }} p
left join (
    select * from (
        {{ anchor_latest({'mnemonic': 'PR_NUM', 'name': 'PR_NUM_Product_ProductNumber'}, 'changingTimepoint') }}
    )
    qualify row_number() over (partition by "PR_NUM_PR_ID" order by "PR_NUM_ChangedAt" desc) = 1
) num on num."PR_NUM_PR_ID" = p."PR_ID"
left join (
    select * from (
        {{ anchor_latest({'mnemonic': 'PR_NAM', 'name': 'PR_NAM_Product_Name'}, 'changingTimepoint') }}
    )
    qualify row_number() over (partition by "PR_NAM_PR_ID" order by "PR_NAM_ChangedAt" desc) = 1
) nam on nam."PR_NAM_PR_ID" = p."PR_ID"
left join (
    select * from (
        {{ anchor_latest({'mnemonic': 'PR_LIN', 'name': 'PR_LIN_Product_ProductLine'}, 'changingTimepoint') }}
    )
    qualify row_number() over (partition by "PR_LIN_PR_ID" order by "PR_LIN_ChangedAt" desc) = 1
) lin on lin."PR_LIN_PR_ID" = p."PR_ID"
left join (
    select * from (
        {{ anchor_latest({'mnemonic': 'PR_COL', 'name': 'PR_COL_Product_Color'}, 'changingTimepoint') }}
    )
    qualify row_number() over (partition by "PR_COL_PR_ID" order by "PR_COL_ChangedAt" desc) = 1
) col on col."PR_COL_PR_ID" = p."PR_ID"
left join (
    select * from (
        {{ anchor_latest({'mnemonic': 'PR_SST', 'name': 'PR_SST_Product_SellStart'}, 'changingTimepoint') }}
    )
    qualify row_number() over (partition by "PR_SST_PR_ID" order by "PR_SST_ChangedAt" desc) = 1
) sst on sst."PR_SST_PR_ID" = p."PR_ID"
left join (
    select * from (
        {{ anchor_latest({'mnemonic': 'PR_SEN', 'name': 'PR_SEN_Product_SellEnd'}, 'changingTimepoint') }}
    )
    qualify row_number() over (partition by "PR_SEN_PR_ID" order by "PR_SEN_ChangedAt" desc) = 1
) sen on sen."PR_SEN_PR_ID" = p."PR_ID"
left join (
    select * from (
        {{ anchor_latest({'mnemonic': 'PR_DIS', 'name': 'PR_DIS_Product_Discontinued'}, 'changingTimepoint') }}
    )
    qualify row_number() over (partition by "PR_DIS_PR_ID" order by "PR_DIS_ChangedAt" desc) = 1
) dis on dis."PR_DIS_PR_ID" = p."PR_ID"
