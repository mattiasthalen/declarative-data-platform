-- PR_NUM_Product_ProductNumber assembled: every annex row with its posit.
{{ config(materialized='view') }}
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
    "mnemonic": "PR_NUM",
    "name": "PR_NUM_Product_ProductNumber",
    "posit": "PR_NUM_Product_ProductNumber_Posit",
    "annex": "PR_NUM_Product_ProductNumber_Annex",
    "column": "product_number",
    "value_type": "varchar(25)",
    "time_type": "timestamp",
    "is_identifier": true
} %}
{{ anchor_assembled(a) }}
