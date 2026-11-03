-- What breaks the keys of PS_NAM_ProductSubcategory_Name_Annex.
{{ config(materialized='view') }}
select 'PS_NAM_ProductSubcategory_Name_Annex' as Construct, 'duplicate primary key' as Violation, json_object('PS_NAM_ID', "PS_NAM_ID", 'PS_NAM_Positor', "PS_NAM_Positor", 'PS_NAM_PositedAt', "PS_NAM_PositedAt") as ViolationKey, count(*) as Occurrences
from {{ ref('PS_NAM_ProductSubcategory_Name_Annex') }}
group by "PS_NAM_ID", "PS_NAM_Positor", "PS_NAM_PositedAt"
having count(*) > 1
union all
select 'PS_NAM_ProductSubcategory_Name_Annex', 'no row in PS_NAM_ProductSubcategory_Name_Posit for PS_NAM_ID', json_object('PS_NAM_ID', c."PS_NAM_ID"), count(*)
from {{ ref('PS_NAM_ProductSubcategory_Name_Annex') }} c
left join {{ ref('PS_NAM_ProductSubcategory_Name_Posit') }} p on p."PS_NAM_ID" = c."PS_NAM_ID"
where p."PS_NAM_ID" is null
group by c."PS_NAM_ID"
