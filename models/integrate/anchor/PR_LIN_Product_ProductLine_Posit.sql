-- The posits of PR_LIN_Product_ProductLine: every value asserted at a ChangedAt.
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
    "mnemonic": "PR_LIN",
    "name": "PR_LIN_Product_ProductLine",
    "identity_column": "PR_LIN_PR_ID",
    "value_column": "PR_LIN_Product_ProductLine",
    "posit": "PR_LIN_Product_ProductLine_Posit",
    "annex": "PR_LIN_Product_ProductLine_Annex",
    "column": "product_line",
    "value_type": "varchar(2)",
    "time_type": "timestamp",
    "is_identifier": false
} %}
{{ anchor_posit(a) }}
