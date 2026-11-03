-- The key of PR_in_PS_contains: positor 0 asserting more than one ProductSubcategory for one Product and ChangedAt at its latest PositedAt.
{{ config(materialized='view') }}
select 'PR_in_PS_contains' as Construct, 'more than one assertion at a time' as Violation,
    json_object('PR_in_PS_contains_Positor', 0, 'PR_ID_in', "PR_ID_in", 'PR_in_PS_contains_ChangedAt', "PR_in_PS_contains_ChangedAt") as ViolationKey,
    count(*) as Occurrences
from (
    {{ anchor_latest({'mnemonic': 'PR_in_PS_contains', 'name': 'PR_in_PS_contains'}) }}
)
group by "PR_ID_in", "PR_in_PS_contains_ChangedAt"
having count(*) > 1
