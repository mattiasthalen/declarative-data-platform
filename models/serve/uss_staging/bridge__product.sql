-- The staged bridge of product: one row per version, keyed like the dimension.
{{ config(materialized='incremental', pre_hook="{{ uss_forget({'entity': 'product', 'anchor': 'PR_Product', 'anchor_mnemonic': 'PR', 'attributes': [{'prefix': 'PR_NUM', 'name': 'PR_NUM_Product_ProductNumber', 'column': 'product__product_number'}, {'prefix': 'PR_NAM', 'name': 'PR_NAM_Product_Name', 'column': 'product__name'}, {'prefix': 'PR_LIN', 'name': 'PR_LIN_Product_ProductLine', 'column': 'product__product_line'}, {'prefix': 'PR_COL', 'name': 'PR_COL_Product_Color', 'column': 'product__color'}, {'prefix': 'PR_SST', 'name': 'PR_SST_Product_SellStart', 'column': 'product__sell_start'}, {'prefix': 'PR_SEN', 'name': 'PR_SEN_Product_SellEnd', 'column': 'product__sell_end'}, {'prefix': 'PR_DIS', 'name': 'PR_DIS_Product_Discontinued', 'column': 'product__discontinued'}]}) }}") }}
{% set e = {'entity': 'product', 'anchor': 'PR_Product', 'anchor_mnemonic': 'PR', 'attributes': [{'prefix': 'PR_NUM', 'name': 'PR_NUM_Product_ProductNumber', 'column': 'product__product_number'}, {'prefix': 'PR_NAM', 'name': 'PR_NAM_Product_Name', 'column': 'product__name'}, {'prefix': 'PR_LIN', 'name': 'PR_LIN_Product_ProductLine', 'column': 'product__product_line'}, {'prefix': 'PR_COL', 'name': 'PR_COL_Product_Color', 'column': 'product__color'}, {'prefix': 'PR_SST', 'name': 'PR_SST_Product_SellStart', 'column': 'product__sell_start'}, {'prefix': 'PR_SEN', 'name': 'PR_SEN_Product_SellEnd', 'column': 'product__sell_end'}, {'prefix': 'PR_DIS', 'name': 'PR_DIS_Product_Discontinued', 'column': 'product__discontinued'}]} %}
with {{ uss_versions(e) }}
select
    'product' as stage,
    coalesce(_key, '[not available]') as _key__product,
    valid_from as _valid_from,
    valid_to as _valid_to
from versions
