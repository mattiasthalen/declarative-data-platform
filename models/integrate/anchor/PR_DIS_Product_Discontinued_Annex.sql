-- The annex of PR_DIS_Product_Discontinued: who asserted or retracted each posit, when, and in which batch.
{{ config(materialized='incremental') }}
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
    "mnemonic": "PR_DIS",
    "name": "PR_DIS_Product_Discontinued",
    "identity_column": "PR_DIS_PR_ID",
    "value_column": "PR_DIS_Product_Discontinued",
    "posit": "PR_DIS_Product_Discontinued_Posit",
    "annex": "PR_DIS_Product_Discontinued_Annex",
    "column": "discontinued_date",
    "value_type": "date",
    "time_type": "timestamp",
    "is_identifier": false
} %}
{{ anchor_annex(a) }}
