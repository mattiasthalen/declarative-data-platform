-- The staged bridge of product: one row per interval over which neither a version of product nor
-- what it reaches over its to-one ties changes, with the PIT key of each version valid for the
-- whole interval; [not available] where a tie has no version (ADR-0038, ADR-0039).
{{ config(materialized='incremental', pre_hook="{{ uss_forget({'entity': 'product', 'anchor': 'PR_Product', 'anchor_mnemonic': 'PR', 'attributes': [{'prefix': 'PR_NUM', 'name': 'PR_NUM_Product_ProductNumber'}, {'prefix': 'PR_NAM', 'name': 'PR_NAM_Product_Name'}, {'prefix': 'PR_LIN', 'name': 'PR_LIN_Product_ProductLine'}, {'prefix': 'PR_COL', 'name': 'PR_COL_Product_Color'}, {'prefix': 'PR_SST', 'name': 'PR_SST_Product_SellStart'}, {'prefix': 'PR_SEN', 'name': 'PR_SEN_Product_SellEnd'}, {'prefix': 'PR_DIS', 'name': 'PR_DIS_Product_Discontinued'}], 'ties': [{'name': 'PR_in_PS_contains', 'identity_column': 'PR_ID_in', 'value_column': 'PS_ID_contains', 'reaches': {'entity': 'product_subcategory', 'anchor': 'PS_ProductSubcategory', 'anchor_mnemonic': 'PS', 'attributes': [{'prefix': 'PS_SID', 'name': 'PS_SID_ProductSubcategory_SourceId'}, {'prefix': 'PS_NAM', 'name': 'PS_NAM_ProductSubcategory_Name'}], 'ties': []}}]}) }}") }}
-- depends_on: {{ ref('PR_in_PS_contains') }}
-- depends_on: {{ ref('PS_ProductSubcategory') }}
-- depends_on: {{ ref('PS_SID_ProductSubcategory_SourceId') }}
-- depends_on: {{ ref('PS_NAM_ProductSubcategory_Name') }}
{% set e = {'entity': 'product', 'anchor': 'PR_Product', 'anchor_mnemonic': 'PR', 'attributes': [{'prefix': 'PR_NUM', 'name': 'PR_NUM_Product_ProductNumber'}, {'prefix': 'PR_NAM', 'name': 'PR_NAM_Product_Name'}, {'prefix': 'PR_LIN', 'name': 'PR_LIN_Product_ProductLine'}, {'prefix': 'PR_COL', 'name': 'PR_COL_Product_Color'}, {'prefix': 'PR_SST', 'name': 'PR_SST_Product_SellStart'}, {'prefix': 'PR_SEN', 'name': 'PR_SEN_Product_SellEnd'}, {'prefix': 'PR_DIS', 'name': 'PR_DIS_Product_Discontinued'}], 'ties': [{'name': 'PR_in_PS_contains', 'identity_column': 'PR_ID_in', 'value_column': 'PS_ID_contains', 'reaches': {'entity': 'product_subcategory', 'anchor': 'PS_ProductSubcategory', 'anchor_mnemonic': 'PS', 'attributes': [{'prefix': 'PS_SID', 'name': 'PS_SID_ProductSubcategory_SourceId'}, {'prefix': 'PS_NAM', 'name': 'PS_NAM_ProductSubcategory_Name'}], 'ties': []}}]} %}
with {{ uss_versions(e) }},
reach_1 as (
    {{ uss_reach(e.ties[0], 'product_subcategory', ['product_subcategory']) }}
),

splits as (
    select id, valid_from from versions
    union
    select id, valid_from from reach_1
),

spans as (
    select id, valid_from,
        lead(valid_from, 1, cast('9999-12-31' as timestamp)) over (partition by id order by valid_from) as valid_to
    from splits
)

select
    'product' as stage,
    v._key as _key__product,
    coalesce(r1._key__product_subcategory, '[not available]') as _key__product_subcategory,
    s.valid_from as _valid_from,
    s.valid_to as _valid_to
from spans s
asof left join versions v on v.id = s.id and v.valid_from <= s.valid_from
asof left join reach_1 r1 on r1.id = s.id and r1.valid_from <= s.valid_from
