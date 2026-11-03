-- The annex of PS_NAM_ProductSubcategory_Name: who asserted or retracted each posit, when, and in which batch.
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
    "identifier_annex": "PS_SID_ProductSubcategory_SourceId_Annex",
    "mnemonic": "PS_NAM",
    "name": "PS_NAM_ProductSubcategory_Name",
    "identity_column": "PS_NAM_PS_ID",
    "value_column": "PS_NAM_ProductSubcategory_Name",
    "posit": "PS_NAM_ProductSubcategory_Name_Posit",
    "annex": "PS_NAM_ProductSubcategory_Name_Annex",
    "column": "name",
    "value_type": "varchar(50)",
    "time_type": "timestamp",
    "is_identifier": false
} %}
{{ anchor_annex(a) }}
