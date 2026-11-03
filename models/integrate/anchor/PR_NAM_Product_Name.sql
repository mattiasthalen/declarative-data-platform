-- PR_NAM_Product_Name assembled: every annex row with its posit.
{{ config(materialized='view') }}
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
    "mnemonic": "PR_NAM",
    "name": "PR_NAM_Product_Name",
    "identity_column": "PR_NAM_PR_ID",
    "value_column": "PR_NAM_Product_Name",
    "posit": "PR_NAM_Product_Name_Posit",
    "annex": "PR_NAM_Product_Name_Annex",
    "column": "name",
    "value_type": "varchar(50)",
    "time_type": "timestamp",
    "is_identifier": false
} %}
{{ anchor_assembled(a) }}
