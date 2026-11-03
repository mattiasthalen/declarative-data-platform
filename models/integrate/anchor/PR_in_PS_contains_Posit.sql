-- The posits of PR_in_PS_contains: every ProductSubcategory a Product was tied to at a ChangedAt.
{{ config(materialized='incremental') }}
-- depends_on: {{ ref('PS_SID_ProductSubcategory_SourceId') }}
{% set a = {
    "anchor": "PR_Product",
    "anchor_mnemonic": "PR",
    "identity_type": "int",
    "source": "adventure_works__products",
    "changed_at": "modified_date",
    "key_column": "product_number",
    "key_type": "varchar(25)",
    "key_view": "key_PR_Product_NUM",
    "identifier_mnemonic": "PR_NUM",
    "identifier_value": "PR_NUM_Product_ProductNumber",
    "identifier_posit": "PR_NUM_Product_ProductNumber_Posit",
    "identifier_annex": "PR_NUM_Product_ProductNumber_Annex",
    "mnemonic": "PR_in_PS_contains",
    "name": "PR_in_PS_contains",
    "identity_column": "PR_ID_in",
    "value_column": "PS_ID_contains",
    "posit": "PR_in_PS_contains_Posit",
    "annex": "PR_in_PS_contains_Annex",
    "column": "product_subcategory_id",
    "value_type": "int",
    "time_type": "timestamp",
    "is_identifier": false,
    "reference_key": "PS_SID_ProductSubcategory_SourceId",
    "reference_key_mnemonic": "PS_SID",
    "reference_id": "PS_SID_PS_ID",
    "reference_key_type": "int"
} %}
{{ anchor_posit(a) }}
