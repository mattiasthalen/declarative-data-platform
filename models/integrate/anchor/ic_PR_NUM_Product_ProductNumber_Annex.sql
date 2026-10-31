-- What breaks the keys of PR_NUM_Product_ProductNumber_Annex.
{{ config(materialized='view') }}
select 'PR_NUM_Product_ProductNumber_Annex' as Construct, 'duplicate primary key' as Violation, json_object('PR_NUM_ID', "PR_NUM_ID", 'PR_NUM_Positor', "PR_NUM_Positor", 'PR_NUM_PositedAt', "PR_NUM_PositedAt") as ViolationKey, count(*) as Occurrences
from {{ ref('PR_NUM_Product_ProductNumber_Annex') }}
group by "PR_NUM_ID", "PR_NUM_Positor", "PR_NUM_PositedAt"
having count(*) > 1
union all
select 'PR_NUM_Product_ProductNumber_Annex', 'no row in PR_NUM_Product_ProductNumber_Posit for PR_NUM_ID', json_object('PR_NUM_ID', c."PR_NUM_ID"), count(*)
from {{ ref('PR_NUM_Product_ProductNumber_Annex') }} c
left join {{ ref('PR_NUM_Product_ProductNumber_Posit') }} p on p."PR_NUM_ID" = c."PR_NUM_ID"
where p."PR_NUM_ID" is null
group by c."PR_NUM_ID"
