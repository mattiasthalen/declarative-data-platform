-- What PR_LIN_Product_ProductLine_Posit and PR_LIN_Product_ProductLine_Annex say together: positor 0 asserting more than one value for one identity and ChangedAt at its latest PositedAt (the model is decisive).
{{ config(materialized='view') }}
select 'PR_LIN_Product_ProductLine' as Construct, 'more than one assertion at a time' as Violation,
    json_object('PR_LIN_Positor', 0, 'PR_LIN_PR_ID', "PR_LIN_PR_ID", 'PR_LIN_ChangedAt', "PR_LIN_ChangedAt") as ViolationKey,
    count(*) as Occurrences
from (
    {{ anchor_latest({'mnemonic': 'PR_LIN', 'name': 'PR_LIN_Product_ProductLine'}) }}
)
group by "PR_LIN_PR_ID", "PR_LIN_ChangedAt"
having count(*) > 1
