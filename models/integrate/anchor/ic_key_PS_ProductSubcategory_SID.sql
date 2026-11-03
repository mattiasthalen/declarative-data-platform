-- Keys of PS_ProductSubcategory that more than one identity has, and identities with more than one key.
{{ config(materialized='view') }}
select 'key_PS_ProductSubcategory_SID' as Construct, 'duplicate natural key' as Violation,
    json_object('PS_SID_ProductSubcategory_SourceId', "PS_SID_ProductSubcategory_SourceId") as ViolationKey, count(*) as Occurrences
from {{ ref('key_PS_ProductSubcategory_SID') }}
group by "PS_SID_ProductSubcategory_SourceId"
having count(*) > 1
union all
select 'key_PS_ProductSubcategory_SID', 'more than one natural key', json_object('PS_ID', "PS_ID"), count(*)
from {{ ref('key_PS_ProductSubcategory_SID') }}
group by "PS_ID"
having count(*) > 1
