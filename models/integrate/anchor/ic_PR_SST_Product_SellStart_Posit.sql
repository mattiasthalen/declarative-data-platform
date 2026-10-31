-- What breaks the keys of PR_SST_Product_SellStart_Posit.
{{ config(materialized='view') }}
select 'PR_SST_Product_SellStart_Posit' as Construct, 'duplicate primary key' as Violation, json_object('PR_SST_ID', "PR_SST_ID") as ViolationKey, count(*) as Occurrences
from {{ ref('PR_SST_Product_SellStart_Posit') }}
group by "PR_SST_ID"
having count(*) > 1
union all
select 'PR_SST_Product_SellStart_Posit' as Construct, 'duplicate unique key' as Violation, json_object('PR_SST_PR_ID', "PR_SST_PR_ID", 'PR_SST_ChangedAt', "PR_SST_ChangedAt", 'PR_SST_Product_SellStart', "PR_SST_Product_SellStart") as ViolationKey, count(*) as Occurrences
from {{ ref('PR_SST_Product_SellStart_Posit') }}
group by "PR_SST_PR_ID", "PR_SST_ChangedAt", "PR_SST_Product_SellStart"
having count(*) > 1
union all
select 'PR_SST_Product_SellStart_Posit', 'no row in PR_Product for PR_SST_PR_ID', json_object('PR_SST_PR_ID', c."PR_SST_PR_ID"), count(*)
from {{ ref('PR_SST_Product_SellStart_Posit') }} c
left join {{ ref('PR_Product') }} p on p."PR_ID" = c."PR_SST_PR_ID"
where p."PR_ID" is null
group by c."PR_SST_PR_ID"
