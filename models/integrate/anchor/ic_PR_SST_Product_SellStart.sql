-- What PR_SST_Product_SellStart_Posit and PR_SST_Product_SellStart_Annex say together: positor 0 asserting more than one value for one identity and ChangedAt at its latest PositedAt (the model is decisive).
{{ config(materialized='view') }}
select 'PR_SST_Product_SellStart' as Construct, 'more than one assertion at a time' as Violation,
    json_object('PR_SST_Positor', 0, 'PR_SST_PR_ID', "PR_SST_PR_ID", 'PR_SST_ChangedAt', "PR_SST_ChangedAt") as ViolationKey,
    count(*) as Occurrences
from (
    {{ anchor_latest({'mnemonic': 'PR_SST', 'name': 'PR_SST_Product_SellStart'}) }}
)
group by "PR_SST_PR_ID", "PR_SST_ChangedAt"
having count(*) > 1
