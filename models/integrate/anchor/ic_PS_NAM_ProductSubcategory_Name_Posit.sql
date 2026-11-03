-- What breaks the keys of PS_NAM_ProductSubcategory_Name_Posit.
{{ config(materialized='view') }}
select 'PS_NAM_ProductSubcategory_Name_Posit' as Construct, 'duplicate primary key' as Violation, json_object('PS_NAM_ID', "PS_NAM_ID") as ViolationKey, count(*) as Occurrences
from {{ ref('PS_NAM_ProductSubcategory_Name_Posit') }}
group by "PS_NAM_ID"
having count(*) > 1
union all
select 'PS_NAM_ProductSubcategory_Name_Posit' as Construct, 'duplicate unique key' as Violation, json_object('PS_NAM_PS_ID', "PS_NAM_PS_ID", 'PS_NAM_ChangedAt', "PS_NAM_ChangedAt", 'PS_NAM_ProductSubcategory_Name', "PS_NAM_ProductSubcategory_Name") as ViolationKey, count(*) as Occurrences
from {{ ref('PS_NAM_ProductSubcategory_Name_Posit') }}
group by "PS_NAM_PS_ID", "PS_NAM_ChangedAt", "PS_NAM_ProductSubcategory_Name"
having count(*) > 1
union all
select 'PS_NAM_ProductSubcategory_Name_Posit', 'no row in PS_ProductSubcategory for PS_NAM_PS_ID', json_object('PS_NAM_PS_ID', c."PS_NAM_PS_ID"), count(*)
from {{ ref('PS_NAM_ProductSubcategory_Name_Posit') }} c
left join {{ ref('PS_ProductSubcategory') }} p on p."PS_ID" = c."PS_NAM_PS_ID"
where p."PS_ID" is null
group by c."PS_NAM_PS_ID"
