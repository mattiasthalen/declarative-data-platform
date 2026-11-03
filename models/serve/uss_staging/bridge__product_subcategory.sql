-- The staged bridge of product_subcategory: one row per version, keyed like the dimension.
{{ config(materialized='incremental', pre_hook="{{ uss_forget({'entity': 'product_subcategory', 'anchor': 'PS_ProductSubcategory', 'anchor_mnemonic': 'PS', 'attributes': [{'prefix': 'PS_SID', 'name': 'PS_SID_ProductSubcategory_SourceId'}, {'prefix': 'PS_NAM', 'name': 'PS_NAM_ProductSubcategory_Name'}]}) }}") }}
{% set e = {'entity': 'product_subcategory', 'anchor': 'PS_ProductSubcategory', 'anchor_mnemonic': 'PS', 'attributes': [{'prefix': 'PS_SID', 'name': 'PS_SID_ProductSubcategory_SourceId'}, {'prefix': 'PS_NAM', 'name': 'PS_NAM_ProductSubcategory_Name'}]} %}
with {{ uss_versions(e) }}
select
    'product_subcategory' as stage,
    _key as _key__product_subcategory,
    valid_from as _valid_from,
    valid_to as _valid_to
from versions
