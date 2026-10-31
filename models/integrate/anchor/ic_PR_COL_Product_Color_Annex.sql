-- What breaks the keys of PR_COL_Product_Color_Annex.
{{ config(materialized='view') }}
select 'PR_COL_Product_Color_Annex' as Construct, 'duplicate primary key' as Violation, json_object('PR_COL_ID', "PR_COL_ID", 'PR_COL_Positor', "PR_COL_Positor", 'PR_COL_PositedAt', "PR_COL_PositedAt") as ViolationKey, count(*) as Occurrences
from {{ ref('PR_COL_Product_Color_Annex') }}
group by "PR_COL_ID", "PR_COL_Positor", "PR_COL_PositedAt"
having count(*) > 1
union all
select 'PR_COL_Product_Color_Annex', 'no row in PR_COL_Product_Color_Posit for PR_COL_ID', json_object('PR_COL_ID', c."PR_COL_ID"), count(*)
from {{ ref('PR_COL_Product_Color_Annex') }} c
left join {{ ref('PR_COL_Product_Color_Posit') }} p on p."PR_COL_ID" = c."PR_COL_ID"
where p."PR_COL_ID" is null
group by c."PR_COL_ID"
