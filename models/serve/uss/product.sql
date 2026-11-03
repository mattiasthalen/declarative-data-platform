-- The product dimension: one row per version on business time, the first from 0001-01-01,
-- plus the ghost rows [not available] and [not applicable].
{{ config(materialized='incremental', on_schema_change='fail', pre_hook="{{ uss_forget({'entity': 'product', 'anchor': 'PR_Product', 'anchor_mnemonic': 'PR', 'attributes': [{'prefix': 'PR_NUM', 'name': 'PR_NUM_Product_ProductNumber'}, {'prefix': 'PR_NAM', 'name': 'PR_NAM_Product_Name'}, {'prefix': 'PR_LIN', 'name': 'PR_LIN_Product_ProductLine'}, {'prefix': 'PR_COL', 'name': 'PR_COL_Product_Color'}, {'prefix': 'PR_SST', 'name': 'PR_SST_Product_SellStart'}, {'prefix': 'PR_SEN', 'name': 'PR_SEN_Product_SellEnd'}, {'prefix': 'PR_DIS', 'name': 'PR_DIS_Product_Discontinued'}], 'ties': [{'name': 'PR_in_PS_contains', 'identity_column': 'PR_ID_in', 'value_column': 'PS_ID_contains', 'reaches': {'entity': 'product_subcategory', 'anchor': 'PS_ProductSubcategory', 'anchor_mnemonic': 'PS', 'attributes': [{'prefix': 'PS_SID', 'name': 'PS_SID_ProductSubcategory_SourceId'}, {'prefix': 'PS_NAM', 'name': 'PS_NAM_ProductSubcategory_Name'}], 'ties': []}}]}) }}") }}
-- depends_on: {{ ref('PR_in_PS_contains') }}
-- depends_on: {{ ref('PS_ProductSubcategory') }}
-- depends_on: {{ ref('PS_SID_ProductSubcategory_SourceId') }}
-- depends_on: {{ ref('PS_NAM_ProductSubcategory_Name') }}
{% set e = {'entity': 'product', 'anchor': 'PR_Product', 'anchor_mnemonic': 'PR', 'attributes': [{'prefix': 'PR_NUM', 'name': 'PR_NUM_Product_ProductNumber'}, {'prefix': 'PR_NAM', 'name': 'PR_NAM_Product_Name'}, {'prefix': 'PR_LIN', 'name': 'PR_LIN_Product_ProductLine'}, {'prefix': 'PR_COL', 'name': 'PR_COL_Product_Color'}, {'prefix': 'PR_SST', 'name': 'PR_SST_Product_SellStart'}, {'prefix': 'PR_SEN', 'name': 'PR_SEN_Product_SellEnd'}, {'prefix': 'PR_DIS', 'name': 'PR_DIS_Product_Discontinued'}], 'ties': [{'name': 'PR_in_PS_contains', 'identity_column': 'PR_ID_in', 'value_column': 'PS_ID_contains', 'reaches': {'entity': 'product_subcategory', 'anchor': 'PS_ProductSubcategory', 'anchor_mnemonic': 'PS', 'attributes': [{'prefix': 'PS_SID', 'name': 'PS_SID_ProductSubcategory_SourceId'}, {'prefix': 'PS_NAM', 'name': 'PS_NAM_ProductSubcategory_Name'}], 'ties': []}}]} %}
with {{ uss_versions(e) }}
select
    v._key as _key__product,
    v.valid_from as product__valid_from,
    v.valid_to as product__valid_to,
    cast(pr_num.value as varchar(25)) as product__product_number,
    cast(pr_nam.value as varchar(50)) as product__name,
    cast(pr_lin.value as varchar(2)) as product__product_line,
    cast(pr_col.value as varchar(15)) as product__color,
    cast(pr_sst.value as date) as product__sell_start,
    cast(pr_sen.value as date) as product__sell_end,
    cast(pr_dis.value as date) as product__discontinued
from versions v
asof left join pr_num on pr_num.id = v.id and pr_num.changed_at <= v.valid_from
asof left join pr_nam on pr_nam.id = v.id and pr_nam.changed_at <= v.valid_from
asof left join pr_lin on pr_lin.id = v.id and pr_lin.changed_at <= v.valid_from
asof left join pr_col on pr_col.id = v.id and pr_col.changed_at <= v.valid_from
asof left join pr_sst on pr_sst.id = v.id and pr_sst.changed_at <= v.valid_from
asof left join pr_sen on pr_sen.id = v.id and pr_sen.changed_at <= v.valid_from
asof left join pr_dis on pr_dis.id = v.id and pr_dis.changed_at <= v.valid_from
{% if not is_incremental() %}
union all
select '[not available]', cast('0001-01-01' as timestamp), cast('9999-12-31' as timestamp), '[not available]', '[not available]', '[not available]', '[not available]', cast(null as date), cast(null as date), cast(null as date)
union all
select '[not applicable]', cast('0001-01-01' as timestamp), cast('9999-12-31' as timestamp), '[not applicable]', '[not applicable]', '[not applicable]', '[not applicable]', cast(null as date), cast(null as date), cast(null as date)
{% endif %}
