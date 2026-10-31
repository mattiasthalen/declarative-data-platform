-- The annex of PR_COL_Product_Color: who asserted or retracted each posit, when, and in which batch.
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
    "mnemonic": "PR_COL",
    "name": "PR_COL_Product_Color",
    "posit": "PR_COL_Product_Color_Posit",
    "annex": "PR_COL_Product_Color_Annex",
    "column": "color",
    "value_type": "varchar(15)",
    "time_type": "timestamp",
    "is_identifier": false
} %}
{{ anchor_annex(a) }}
