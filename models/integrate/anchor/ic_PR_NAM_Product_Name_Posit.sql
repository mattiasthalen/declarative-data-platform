-- What breaks the keys of PR_NAM_Product_Name_Posit.
{{ config(materialized='view') }}
select 'PR_NAM_Product_Name_Posit' as Construct, 'duplicate primary key' as Violation, json_object('PR_NAM_ID', "PR_NAM_ID") as ViolationKey, count(*) as Occurrences
from {{ ref('PR_NAM_Product_Name_Posit') }}
group by "PR_NAM_ID"
having count(*) > 1
union all
select 'PR_NAM_Product_Name_Posit' as Construct, 'duplicate unique key' as Violation, json_object('PR_NAM_PR_ID', "PR_NAM_PR_ID", 'PR_NAM_ChangedAt', "PR_NAM_ChangedAt", 'PR_NAM_Product_Name', "PR_NAM_Product_Name") as ViolationKey, count(*) as Occurrences
from {{ ref('PR_NAM_Product_Name_Posit') }}
group by "PR_NAM_PR_ID", "PR_NAM_ChangedAt", "PR_NAM_Product_Name"
having count(*) > 1
union all
select 'PR_NAM_Product_Name_Posit', 'no row in PR_Product for PR_NAM_PR_ID', json_object('PR_NAM_PR_ID', c."PR_NAM_PR_ID"), count(*)
from {{ ref('PR_NAM_Product_Name_Posit') }} c
left join {{ ref('PR_Product') }} p on p."PR_ID" = c."PR_NAM_PR_ID"
where p."PR_ID" is null
group by c."PR_NAM_PR_ID"
