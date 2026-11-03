-- What PS_NAM_ProductSubcategory_Name_Posit and PS_NAM_ProductSubcategory_Name_Annex say together: positor 0 asserting more than one value for one identity and ChangedAt at its latest PositedAt (the model is decisive).
{{ config(materialized='view') }}
select 'PS_NAM_ProductSubcategory_Name' as Construct, 'more than one assertion at a time' as Violation,
    json_object('PS_NAM_Positor', 0, 'PS_NAM_PS_ID', "PS_NAM_PS_ID", 'PS_NAM_ChangedAt', "PS_NAM_ChangedAt") as ViolationKey,
    count(*) as Occurrences
from (
    {{ anchor_latest({'mnemonic': 'PS_NAM', 'name': 'PS_NAM_ProductSubcategory_Name'}) }}
)
group by "PS_NAM_PS_ID", "PS_NAM_ChangedAt"
having count(*) > 1
