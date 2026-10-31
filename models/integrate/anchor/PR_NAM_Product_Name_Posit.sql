-- The posits of PR_NAM_Product_Name: every value asserted at a ChangedAt.
{{ config(materialized='incremental') }}
{% set a = {
    "anchor": "PR_Product",
    "anchor_mnemonic": "PR",
    "identity_type": "int",
    "source": "adventure_works__products",
    "changed_at": "modified_date",
    "key_column": "product_number",
    "key_view": "key_PR_Product_NUM",
    "identifier_mnemonic": "PR_NUM",
    "identifier_value": "PR_NUM_Product_ProductNumber",
    "identifier_posit": "PR_NUM_Product_ProductNumber_Posit",
    "identifier_annex": "PR_NUM_Product_ProductNumber_Annex",
    "mnemonic": "PR_NAM",
    "name": "PR_NAM_Product_Name",
    "posit": "PR_NAM_Product_Name_Posit",
    "annex": "PR_NAM_Product_Name_Annex",
    "column": "name",
    "value_type": "varchar(50)",
    "time_type": "timestamp",
    "is_identifier": false
} %}
{{ anchor_posit(a) }}
