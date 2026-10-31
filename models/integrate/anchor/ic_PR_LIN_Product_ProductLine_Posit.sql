-- What breaks the keys of PR_LIN_Product_ProductLine_Posit.
{{ config(materialized='view') }}
select 'PR_LIN_Product_ProductLine_Posit' as Construct, 'duplicate primary key' as Violation, json_object('PR_LIN_ID', "PR_LIN_ID") as ViolationKey, count(*) as Occurrences
from {{ ref('PR_LIN_Product_ProductLine_Posit') }}
group by "PR_LIN_ID"
having count(*) > 1
union all
select 'PR_LIN_Product_ProductLine_Posit' as Construct, 'duplicate unique key' as Violation, json_object('PR_LIN_PR_ID', "PR_LIN_PR_ID", 'PR_LIN_ChangedAt', "PR_LIN_ChangedAt", 'PR_LIN_Product_ProductLine', "PR_LIN_Product_ProductLine") as ViolationKey, count(*) as Occurrences
from {{ ref('PR_LIN_Product_ProductLine_Posit') }}
group by "PR_LIN_PR_ID", "PR_LIN_ChangedAt", "PR_LIN_Product_ProductLine"
having count(*) > 1
union all
select 'PR_LIN_Product_ProductLine_Posit', 'no row in PR_Product for PR_LIN_PR_ID', json_object('PR_LIN_PR_ID', c."PR_LIN_PR_ID"), count(*)
from {{ ref('PR_LIN_Product_ProductLine_Posit') }} c
left join {{ ref('PR_Product') }} p on p."PR_ID" = c."PR_LIN_PR_ID"
where p."PR_ID" is null
group by c."PR_LIN_PR_ID"
