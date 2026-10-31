-- The staged bridge of product: one row per version, keyed like the dimension.
{{ config(materialized='incremental', pre_hook="{{ uss_forget({'entity': 'product', 'anchor': 'PR_Product', 'anchor_mnemonic': 'PR', 'attributes': [{'prefix': 'PR_NUM', 'name': 'PR_NUM_Product_ProductNumber'}, {'prefix': 'PR_NAM', 'name': 'PR_NAM_Product_Name'}, {'prefix': 'PR_LIN', 'name': 'PR_LIN_Product_ProductLine'}, {'prefix': 'PR_COL', 'name': 'PR_COL_Product_Color'}, {'prefix': 'PR_SST', 'name': 'PR_SST_Product_SellStart'}, {'prefix': 'PR_SEN', 'name': 'PR_SEN_Product_SellEnd'}, {'prefix': 'PR_DIS', 'name': 'PR_DIS_Product_Discontinued'}]}) }}") }}
{% set e = {'entity': 'product', 'anchor': 'PR_Product', 'anchor_mnemonic': 'PR', 'attributes': [{'prefix': 'PR_NUM', 'name': 'PR_NUM_Product_ProductNumber'}, {'prefix': 'PR_NAM', 'name': 'PR_NAM_Product_Name'}, {'prefix': 'PR_LIN', 'name': 'PR_LIN_Product_ProductLine'}, {'prefix': 'PR_COL', 'name': 'PR_COL_Product_Color'}, {'prefix': 'PR_SST', 'name': 'PR_SST_Product_SellStart'}, {'prefix': 'PR_SEN', 'name': 'PR_SEN_Product_SellEnd'}, {'prefix': 'PR_DIS', 'name': 'PR_DIS_Product_Discontinued'}]} %}
with {{ uss_versions(e) }}
select
    'product' as stage,
    _key as _key__product,
    valid_from as _valid_from,
    valid_to as _valid_to
from versions
