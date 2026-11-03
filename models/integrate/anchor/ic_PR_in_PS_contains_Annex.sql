-- What breaks the keys of PR_in_PS_contains_Annex.
{{ config(materialized='view') }}
select 'PR_in_PS_contains_Annex' as Construct, 'duplicate primary key' as Violation, json_object('PR_in_PS_contains_ID', "PR_in_PS_contains_ID", 'PR_in_PS_contains_Positor', "PR_in_PS_contains_Positor", 'PR_in_PS_contains_PositedAt', "PR_in_PS_contains_PositedAt") as ViolationKey, count(*) as Occurrences
from {{ ref('PR_in_PS_contains_Annex') }}
group by "PR_in_PS_contains_ID", "PR_in_PS_contains_Positor", "PR_in_PS_contains_PositedAt"
having count(*) > 1
union all
select 'PR_in_PS_contains_Annex', 'no row in PR_in_PS_contains_Posit for PR_in_PS_contains_ID', json_object('PR_in_PS_contains_ID', c."PR_in_PS_contains_ID"), count(*)
from {{ ref('PR_in_PS_contains_Annex') }} c
left join {{ ref('PR_in_PS_contains_Posit') }} p on p."PR_in_PS_contains_ID" = c."PR_in_PS_contains_ID"
where p."PR_in_PS_contains_ID" is null
group by c."PR_in_PS_contains_ID"
