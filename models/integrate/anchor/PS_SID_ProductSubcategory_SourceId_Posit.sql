-- The posits of PS_SID_ProductSubcategory_SourceId: every value asserted at a ChangedAt.
{{ config(materialized='incremental') }}
-- depends_on: {{ ref('PS_ProductSubcategory') }}
{% set a = {
    "anchor": "PS_ProductSubcategory",
    "anchor_mnemonic": "PS",
    "identity_type": "int",
    "source": "adventure_works__product_subcategories",
    "changed_at": "modified_date",
    "key_column": "product_subcategory_id",
    "key_type": "int",
    "key_view": "key_PS_ProductSubcategory_SID",
    "identifier_mnemonic": "PS_SID",
    "identifier_value": "PS_SID_ProductSubcategory_SourceId",
    "identifier_posit": "PS_SID_ProductSubcategory_SourceId_Posit",
    "identifier_annex": "PS_SID_ProductSubcategory_SourceId_Annex",
    "mnemonic": "PS_SID",
    "name": "PS_SID_ProductSubcategory_SourceId",
    "identity_column": "PS_SID_PS_ID",
    "value_column": "PS_SID_ProductSubcategory_SourceId",
    "posit": "PS_SID_ProductSubcategory_SourceId_Posit",
    "annex": "PS_SID_ProductSubcategory_SourceId_Annex",
    "column": "product_subcategory_id",
    "value_type": "int",
    "time_type": "timestamp",
    "is_identifier": true
} %}
{{ anchor_posit(a) }}
