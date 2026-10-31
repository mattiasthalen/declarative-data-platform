-- What PR_COL_Product_Color_Posit and PR_COL_Product_Color_Annex say together: positor 0 asserting more than one value for one identity and ChangedAt at its latest PositedAt (the model is decisive).
{{ config(materialized='view') }}
select 'PR_COL_Product_Color' as Construct, 'more than one assertion at a time' as Violation,
    json_object('PR_COL_Positor', 0, 'PR_COL_PR_ID', "PR_COL_PR_ID", 'PR_COL_ChangedAt', "PR_COL_ChangedAt") as ViolationKey,
    count(*) as Occurrences
from (
    {{ anchor_latest({'mnemonic': 'PR_COL', 'name': 'PR_COL_Product_Color'}) }}
)
group by "PR_COL_PR_ID", "PR_COL_ChangedAt"
having count(*) > 1
