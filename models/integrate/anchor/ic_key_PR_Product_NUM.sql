-- Keys of PR_Product that more than one identity has, and identities with more than one key.
{{ config(materialized='view') }}
select 'key_PR_Product_NUM' as Construct, 'duplicate natural key' as Violation,
    json_object('PR_NUM_Product_ProductNumber', "PR_NUM_Product_ProductNumber") as ViolationKey, count(*) as Occurrences
from {{ ref('key_PR_Product_NUM') }}
group by "PR_NUM_Product_ProductNumber"
having count(*) > 1
union all
select 'key_PR_Product_NUM', 'more than one natural key', json_object('PR_ID', "PR_ID"), count(*)
from {{ ref('key_PR_Product_NUM') }}
group by "PR_ID"
having count(*) > 1
