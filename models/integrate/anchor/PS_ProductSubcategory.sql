-- The PS_ProductSubcategory anchor: one identity per SourceId (ADR-0005).
{{ config(materialized='incremental') }}
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
    "identifier_annex": "PS_SID_ProductSubcategory_SourceId_Annex"
} %}
{{ anchor_anchor(a) }}
