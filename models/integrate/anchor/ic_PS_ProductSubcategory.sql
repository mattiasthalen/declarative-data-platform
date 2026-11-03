-- What breaks the keys of PS_ProductSubcategory.
{{ config(materialized='view') }}
select 'PS_ProductSubcategory' as Construct, 'duplicate primary key' as Violation, json_object('PS_ID', "PS_ID") as ViolationKey, count(*) as Occurrences
from {{ ref('PS_ProductSubcategory') }}
group by "PS_ID"
having count(*) > 1
