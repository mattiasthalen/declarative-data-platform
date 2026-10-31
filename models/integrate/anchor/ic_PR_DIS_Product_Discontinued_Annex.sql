-- What breaks the keys of PR_DIS_Product_Discontinued_Annex.
{{ config(materialized='view') }}
select 'PR_DIS_Product_Discontinued_Annex' as Construct, 'duplicate primary key' as Violation, json_object('PR_DIS_ID', "PR_DIS_ID", 'PR_DIS_Positor', "PR_DIS_Positor", 'PR_DIS_PositedAt', "PR_DIS_PositedAt") as ViolationKey, count(*) as Occurrences
from {{ ref('PR_DIS_Product_Discontinued_Annex') }}
group by "PR_DIS_ID", "PR_DIS_Positor", "PR_DIS_PositedAt"
having count(*) > 1
union all
select 'PR_DIS_Product_Discontinued_Annex', 'no row in PR_DIS_Product_Discontinued_Posit for PR_DIS_ID', json_object('PR_DIS_ID', c."PR_DIS_ID"), count(*)
from {{ ref('PR_DIS_Product_Discontinued_Annex') }} c
left join {{ ref('PR_DIS_Product_Discontinued_Posit') }} p on p."PR_DIS_ID" = c."PR_DIS_ID"
where p."PR_DIS_ID" is null
group by c."PR_DIS_ID"
