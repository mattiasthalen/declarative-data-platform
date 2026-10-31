-- What breaks the keys of PR_NUM_Product_ProductNumber_Posit.
{{ config(materialized='view') }}
select 'PR_NUM_Product_ProductNumber_Posit' as Construct, 'duplicate primary key' as Violation, json_object('PR_NUM_ID', "PR_NUM_ID") as ViolationKey, count(*) as Occurrences
from {{ ref('PR_NUM_Product_ProductNumber_Posit') }}
group by "PR_NUM_ID"
having count(*) > 1
union all
select 'PR_NUM_Product_ProductNumber_Posit' as Construct, 'duplicate unique key' as Violation, json_object('PR_NUM_PR_ID', "PR_NUM_PR_ID", 'PR_NUM_ChangedAt', "PR_NUM_ChangedAt", 'PR_NUM_Product_ProductNumber', "PR_NUM_Product_ProductNumber") as ViolationKey, count(*) as Occurrences
from {{ ref('PR_NUM_Product_ProductNumber_Posit') }}
group by "PR_NUM_PR_ID", "PR_NUM_ChangedAt", "PR_NUM_Product_ProductNumber"
having count(*) > 1
union all
select 'PR_NUM_Product_ProductNumber_Posit', 'no row in PR_Product for PR_NUM_PR_ID', json_object('PR_NUM_PR_ID', c."PR_NUM_PR_ID"), count(*)
from {{ ref('PR_NUM_Product_ProductNumber_Posit') }} c
left join {{ ref('PR_Product') }} p on p."PR_ID" = c."PR_NUM_PR_ID"
where p."PR_ID" is null
group by c."PR_NUM_PR_ID"
