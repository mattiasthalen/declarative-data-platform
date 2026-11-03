-- What breaks the keys of PS_SID_ProductSubcategory_SourceId_Posit.
{{ config(materialized='view') }}
select 'PS_SID_ProductSubcategory_SourceId_Posit' as Construct, 'duplicate primary key' as Violation, json_object('PS_SID_ID', "PS_SID_ID") as ViolationKey, count(*) as Occurrences
from {{ ref('PS_SID_ProductSubcategory_SourceId_Posit') }}
group by "PS_SID_ID"
having count(*) > 1
union all
select 'PS_SID_ProductSubcategory_SourceId_Posit' as Construct, 'duplicate unique key' as Violation, json_object('PS_SID_PS_ID', "PS_SID_PS_ID", 'PS_SID_ChangedAt', "PS_SID_ChangedAt", 'PS_SID_ProductSubcategory_SourceId', "PS_SID_ProductSubcategory_SourceId") as ViolationKey, count(*) as Occurrences
from {{ ref('PS_SID_ProductSubcategory_SourceId_Posit') }}
group by "PS_SID_PS_ID", "PS_SID_ChangedAt", "PS_SID_ProductSubcategory_SourceId"
having count(*) > 1
union all
select 'PS_SID_ProductSubcategory_SourceId_Posit', 'no row in PS_ProductSubcategory for PS_SID_PS_ID', json_object('PS_SID_PS_ID', c."PS_SID_PS_ID"), count(*)
from {{ ref('PS_SID_ProductSubcategory_SourceId_Posit') }} c
left join {{ ref('PS_ProductSubcategory') }} p on p."PS_ID" = c."PS_SID_PS_ID"
where p."PS_ID" is null
group by c."PS_SID_PS_ID"
