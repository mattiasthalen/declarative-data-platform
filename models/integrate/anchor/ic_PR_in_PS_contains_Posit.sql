-- What breaks the keys of PR_in_PS_contains_Posit.
{{ config(materialized='view') }}
select 'PR_in_PS_contains_Posit' as Construct, 'duplicate primary key' as Violation, json_object('PR_in_PS_contains_ID', "PR_in_PS_contains_ID") as ViolationKey, count(*) as Occurrences
from {{ ref('PR_in_PS_contains_Posit') }}
group by "PR_in_PS_contains_ID"
having count(*) > 1
union all
select 'PR_in_PS_contains_Posit' as Construct, 'duplicate unique key' as Violation, json_object('PR_ID_in', "PR_ID_in", 'PR_in_PS_contains_ChangedAt', "PR_in_PS_contains_ChangedAt", 'PS_ID_contains', "PS_ID_contains") as ViolationKey, count(*) as Occurrences
from {{ ref('PR_in_PS_contains_Posit') }}
group by "PR_ID_in", "PR_in_PS_contains_ChangedAt", "PS_ID_contains"
having count(*) > 1
union all
select 'PR_in_PS_contains_Posit', 'no row in PR_Product for PR_ID_in', json_object('PR_ID_in', c."PR_ID_in"), count(*)
from {{ ref('PR_in_PS_contains_Posit') }} c
left join {{ ref('PR_Product') }} p on p."PR_ID" = c."PR_ID_in"
where p."PR_ID" is null
group by c."PR_ID_in"
union all
select 'PR_in_PS_contains_Posit', 'no row in PS_ProductSubcategory for PS_ID_contains', json_object('PS_ID_contains', c."PS_ID_contains"), count(*)
from {{ ref('PR_in_PS_contains_Posit') }} c
left join {{ ref('PS_ProductSubcategory') }} p on p."PS_ID" = c."PS_ID_contains"
where p."PS_ID" is null
group by c."PS_ID_contains"
