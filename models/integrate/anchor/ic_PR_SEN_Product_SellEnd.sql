-- What PR_SEN_Product_SellEnd_Posit and PR_SEN_Product_SellEnd_Annex say together: positor 0 asserting more than one value for one identity and ChangedAt at its latest PositedAt (the model is decisive).
{{ config(materialized='view') }}
select 'PR_SEN_Product_SellEnd' as Construct, 'more than one assertion at a time' as Violation,
    json_object('PR_SEN_Positor', 0, 'PR_SEN_PR_ID', "PR_SEN_PR_ID", 'PR_SEN_ChangedAt', "PR_SEN_ChangedAt") as ViolationKey,
    count(*) as Occurrences
from (
    {{ anchor_latest({'mnemonic': 'PR_SEN', 'name': 'PR_SEN_Product_SellEnd'}) }}
)
group by "PR_SEN_PR_ID", "PR_SEN_ChangedAt"
having count(*) > 1
