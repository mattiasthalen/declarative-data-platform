-- PR_DIS_Product_Discontinued assembled: every annex row with its posit.
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
    "mnemonic": "PR_DIS",
    "name": "PR_DIS_Product_Discontinued",
    "posit": "PR_DIS_Product_Discontinued_Posit",
    "annex": "PR_DIS_Product_Discontinued_Annex",
    "column": "discontinued_date",
    "value_type": "date",
    "time_type": "timestamp",
    "is_identifier": false
} %}
{{ anchor_assembled(a) }}
