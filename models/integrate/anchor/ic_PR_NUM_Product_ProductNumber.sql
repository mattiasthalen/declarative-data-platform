-- What PR_NUM_Product_ProductNumber_Posit and PR_NUM_Product_ProductNumber_Annex say together: positor 0 asserting more than one value for one identity and ChangedAt at its latest PositedAt (the model is decisive).
{{ config(materialized='view') }}
select 'PR_NUM_Product_ProductNumber' as Construct, 'more than one assertion at a time' as Violation,
    json_object('PR_NUM_Positor', 0, 'PR_NUM_PR_ID', "PR_NUM_PR_ID", 'PR_NUM_ChangedAt', "PR_NUM_ChangedAt") as ViolationKey,
    count(*) as Occurrences
from (
    {{ anchor_latest({'mnemonic': 'PR_NUM', 'name': 'PR_NUM_Product_ProductNumber'}) }}
)
group by "PR_NUM_PR_ID", "PR_NUM_ChangedAt"
having count(*) > 1
