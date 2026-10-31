-- What breaks the keys of PR_LIN_Product_ProductLine_Annex.
{{ config(materialized='view') }}
select 'PR_LIN_Product_ProductLine_Annex' as Construct, 'duplicate primary key' as Violation, json_object('PR_LIN_ID', "PR_LIN_ID", 'PR_LIN_Positor', "PR_LIN_Positor", 'PR_LIN_PositedAt', "PR_LIN_PositedAt") as ViolationKey, count(*) as Occurrences
from {{ ref('PR_LIN_Product_ProductLine_Annex') }}
group by "PR_LIN_ID", "PR_LIN_Positor", "PR_LIN_PositedAt"
having count(*) > 1
union all
select 'PR_LIN_Product_ProductLine_Annex', 'no row in PR_LIN_Product_ProductLine_Posit for PR_LIN_ID', json_object('PR_LIN_ID', c."PR_LIN_ID"), count(*)
from {{ ref('PR_LIN_Product_ProductLine_Annex') }} c
left join {{ ref('PR_LIN_Product_ProductLine_Posit') }} p on p."PR_LIN_ID" = c."PR_LIN_ID"
where p."PR_LIN_ID" is null
group by c."PR_LIN_ID"
