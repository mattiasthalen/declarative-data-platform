-- What PS_SID_ProductSubcategory_SourceId_Posit and PS_SID_ProductSubcategory_SourceId_Annex say together: positor 0 asserting more than one value for one identity and ChangedAt at its latest PositedAt (the model is decisive).
{{ config(materialized='view') }}
select 'PS_SID_ProductSubcategory_SourceId' as Construct, 'more than one assertion at a time' as Violation,
    json_object('PS_SID_Positor', 0, 'PS_SID_PS_ID', "PS_SID_PS_ID", 'PS_SID_ChangedAt', "PS_SID_ChangedAt") as ViolationKey,
    count(*) as Occurrences
from (
    {{ anchor_latest({'mnemonic': 'PS_SID', 'name': 'PS_SID_ProductSubcategory_SourceId'}) }}
)
group by "PS_SID_PS_ID", "PS_SID_ChangedAt"
having count(*) > 1
