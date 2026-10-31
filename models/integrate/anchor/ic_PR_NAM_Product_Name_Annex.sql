-- What breaks the keys of PR_NAM_Product_Name_Annex.
{{ config(materialized='view') }}
select 'PR_NAM_Product_Name_Annex' as Construct, 'duplicate primary key' as Violation, json_object('PR_NAM_ID', "PR_NAM_ID", 'PR_NAM_Positor', "PR_NAM_Positor", 'PR_NAM_PositedAt', "PR_NAM_PositedAt") as ViolationKey, count(*) as Occurrences
from {{ ref('PR_NAM_Product_Name_Annex') }}
group by "PR_NAM_ID", "PR_NAM_Positor", "PR_NAM_PositedAt"
having count(*) > 1
union all
select 'PR_NAM_Product_Name_Annex', 'no row in PR_NAM_Product_Name_Posit for PR_NAM_ID', json_object('PR_NAM_ID', c."PR_NAM_ID"), count(*)
from {{ ref('PR_NAM_Product_Name_Annex') }} c
left join {{ ref('PR_NAM_Product_Name_Posit') }} p on p."PR_NAM_ID" = c."PR_NAM_ID"
where p."PR_NAM_ID" is null
group by c."PR_NAM_ID"
