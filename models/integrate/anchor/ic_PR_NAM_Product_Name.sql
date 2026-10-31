-- What PR_NAM_Product_Name_Posit and PR_NAM_Product_Name_Annex say together: positor 0 asserting more than one value for one identity and ChangedAt at its latest PositedAt (the model is decisive).
{{ config(materialized='view') }}
select 'PR_NAM_Product_Name' as Construct, 'more than one assertion at a time' as Violation,
    json_object('PR_NAM_Positor', 0, 'PR_NAM_PR_ID', "PR_NAM_PR_ID", 'PR_NAM_ChangedAt', "PR_NAM_ChangedAt") as ViolationKey,
    count(*) as Occurrences
from (
    {{ anchor_latest({'mnemonic': 'PR_NAM', 'name': 'PR_NAM_Product_Name'}) }}
)
group by "PR_NAM_PR_ID", "PR_NAM_ChangedAt"
having count(*) > 1
