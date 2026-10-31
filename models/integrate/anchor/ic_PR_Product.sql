-- What breaks the keys of PR_Product.
{{ config(materialized='view') }}
select 'PR_Product' as Construct, 'duplicate primary key' as Violation, json_object('PR_ID', "PR_ID") as ViolationKey, count(*) as Occurrences
from {{ ref('PR_Product') }}
group by "PR_ID"
having count(*) > 1
