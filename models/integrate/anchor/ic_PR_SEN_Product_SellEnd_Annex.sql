-- What breaks the keys of PR_SEN_Product_SellEnd_Annex.
{{ config(materialized='view') }}
select 'PR_SEN_Product_SellEnd_Annex' as Construct, 'duplicate primary key' as Violation, json_object('PR_SEN_ID', "PR_SEN_ID", 'PR_SEN_Positor', "PR_SEN_Positor", 'PR_SEN_PositedAt', "PR_SEN_PositedAt") as ViolationKey, count(*) as Occurrences
from {{ ref('PR_SEN_Product_SellEnd_Annex') }}
group by "PR_SEN_ID", "PR_SEN_Positor", "PR_SEN_PositedAt"
having count(*) > 1
union all
select 'PR_SEN_Product_SellEnd_Annex', 'no row in PR_SEN_Product_SellEnd_Posit for PR_SEN_ID', json_object('PR_SEN_ID', c."PR_SEN_ID"), count(*)
from {{ ref('PR_SEN_Product_SellEnd_Annex') }} c
left join {{ ref('PR_SEN_Product_SellEnd_Posit') }} p on p."PR_SEN_ID" = c."PR_SEN_ID"
where p."PR_SEN_ID" is null
group by c."PR_SEN_ID"
