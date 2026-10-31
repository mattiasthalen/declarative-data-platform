-- What breaks the keys of PR_DIS_Product_Discontinued_Posit.
{{ config(materialized='view') }}
select 'PR_DIS_Product_Discontinued_Posit' as Construct, 'duplicate primary key' as Violation, json_object('PR_DIS_ID', "PR_DIS_ID") as ViolationKey, count(*) as Occurrences
from {{ ref('PR_DIS_Product_Discontinued_Posit') }}
group by "PR_DIS_ID"
having count(*) > 1
union all
select 'PR_DIS_Product_Discontinued_Posit' as Construct, 'duplicate unique key' as Violation, json_object('PR_DIS_PR_ID', "PR_DIS_PR_ID", 'PR_DIS_ChangedAt', "PR_DIS_ChangedAt", 'PR_DIS_Product_Discontinued', "PR_DIS_Product_Discontinued") as ViolationKey, count(*) as Occurrences
from {{ ref('PR_DIS_Product_Discontinued_Posit') }}
group by "PR_DIS_PR_ID", "PR_DIS_ChangedAt", "PR_DIS_Product_Discontinued"
having count(*) > 1
union all
select 'PR_DIS_Product_Discontinued_Posit', 'no row in PR_Product for PR_DIS_PR_ID', json_object('PR_DIS_PR_ID', c."PR_DIS_PR_ID"), count(*)
from {{ ref('PR_DIS_Product_Discontinued_Posit') }} c
left join {{ ref('PR_Product') }} p on p."PR_ID" = c."PR_DIS_PR_ID"
where p."PR_ID" is null
group by c."PR_DIS_PR_ID"
