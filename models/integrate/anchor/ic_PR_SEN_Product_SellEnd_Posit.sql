-- What breaks the keys of PR_SEN_Product_SellEnd_Posit.
{{ config(materialized='view') }}
select 'PR_SEN_Product_SellEnd_Posit' as Construct, 'duplicate primary key' as Violation, json_object('PR_SEN_ID', "PR_SEN_ID") as ViolationKey, count(*) as Occurrences
from {{ ref('PR_SEN_Product_SellEnd_Posit') }}
group by "PR_SEN_ID"
having count(*) > 1
union all
select 'PR_SEN_Product_SellEnd_Posit' as Construct, 'duplicate unique key' as Violation, json_object('PR_SEN_PR_ID', "PR_SEN_PR_ID", 'PR_SEN_ChangedAt', "PR_SEN_ChangedAt", 'PR_SEN_Product_SellEnd', "PR_SEN_Product_SellEnd") as ViolationKey, count(*) as Occurrences
from {{ ref('PR_SEN_Product_SellEnd_Posit') }}
group by "PR_SEN_PR_ID", "PR_SEN_ChangedAt", "PR_SEN_Product_SellEnd"
having count(*) > 1
union all
select 'PR_SEN_Product_SellEnd_Posit', 'no row in PR_Product for PR_SEN_PR_ID', json_object('PR_SEN_PR_ID', c."PR_SEN_PR_ID"), count(*)
from {{ ref('PR_SEN_Product_SellEnd_Posit') }} c
left join {{ ref('PR_Product') }} p on p."PR_ID" = c."PR_SEN_PR_ID"
where p."PR_ID" is null
group by c."PR_SEN_PR_ID"
