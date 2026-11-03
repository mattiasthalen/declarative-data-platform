-- What breaks the keys of PS_SID_ProductSubcategory_SourceId_Annex.
{{ config(materialized='view') }}
select 'PS_SID_ProductSubcategory_SourceId_Annex' as Construct, 'duplicate primary key' as Violation, json_object('PS_SID_ID', "PS_SID_ID", 'PS_SID_Positor', "PS_SID_Positor", 'PS_SID_PositedAt', "PS_SID_PositedAt") as ViolationKey, count(*) as Occurrences
from {{ ref('PS_SID_ProductSubcategory_SourceId_Annex') }}
group by "PS_SID_ID", "PS_SID_Positor", "PS_SID_PositedAt"
having count(*) > 1
union all
select 'PS_SID_ProductSubcategory_SourceId_Annex', 'no row in PS_SID_ProductSubcategory_SourceId_Posit for PS_SID_ID', json_object('PS_SID_ID', c."PS_SID_ID"), count(*)
from {{ ref('PS_SID_ProductSubcategory_SourceId_Annex') }} c
left join {{ ref('PS_SID_ProductSubcategory_SourceId_Posit') }} p on p."PS_SID_ID" = c."PS_SID_ID"
where p."PS_SID_ID" is null
group by c."PS_SID_ID"
