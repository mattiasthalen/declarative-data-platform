-- What breaks the keys of PR_COL_Product_Color_Posit.
{{ config(materialized='view') }}
select 'PR_COL_Product_Color_Posit' as Construct, 'duplicate primary key' as Violation, json_object('PR_COL_ID', "PR_COL_ID") as ViolationKey, count(*) as Occurrences
from {{ ref('PR_COL_Product_Color_Posit') }}
group by "PR_COL_ID"
having count(*) > 1
union all
select 'PR_COL_Product_Color_Posit' as Construct, 'duplicate unique key' as Violation, json_object('PR_COL_PR_ID', "PR_COL_PR_ID", 'PR_COL_ChangedAt', "PR_COL_ChangedAt", 'PR_COL_Product_Color', "PR_COL_Product_Color") as ViolationKey, count(*) as Occurrences
from {{ ref('PR_COL_Product_Color_Posit') }}
group by "PR_COL_PR_ID", "PR_COL_ChangedAt", "PR_COL_Product_Color"
having count(*) > 1
union all
select 'PR_COL_Product_Color_Posit', 'no row in PR_Product for PR_COL_PR_ID', json_object('PR_COL_PR_ID', c."PR_COL_PR_ID"), count(*)
from {{ ref('PR_COL_Product_Color_Posit') }} c
left join {{ ref('PR_Product') }} p on p."PR_ID" = c."PR_COL_PR_ID"
where p."PR_ID" is null
group by c."PR_COL_PR_ID"
