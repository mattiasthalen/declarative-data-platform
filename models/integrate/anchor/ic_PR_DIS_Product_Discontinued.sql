-- What PR_DIS_Product_Discontinued_Posit and PR_DIS_Product_Discontinued_Annex say together: positor 0 asserting more than one value for one identity and ChangedAt at its latest PositedAt (the model is decisive).
{{ config(materialized='view') }}
select 'PR_DIS_Product_Discontinued' as Construct, 'more than one assertion at a time' as Violation,
    json_object('PR_DIS_Positor', 0, 'PR_DIS_PR_ID', "PR_DIS_PR_ID", 'PR_DIS_ChangedAt', "PR_DIS_ChangedAt") as ViolationKey,
    count(*) as Occurrences
from (
    {{ anchor_latest({'mnemonic': 'PR_DIS', 'name': 'PR_DIS_Product_Discontinued'}) }}
)
group by "PR_DIS_PR_ID", "PR_DIS_ChangedAt"
having count(*) > 1
