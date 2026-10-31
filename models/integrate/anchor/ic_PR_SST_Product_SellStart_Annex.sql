-- What breaks the keys of PR_SST_Product_SellStart_Annex.
{{ config(materialized='view') }}
select 'PR_SST_Product_SellStart_Annex' as Construct, 'duplicate primary key' as Violation, json_object('PR_SST_ID', "PR_SST_ID", 'PR_SST_Positor', "PR_SST_Positor", 'PR_SST_PositedAt', "PR_SST_PositedAt") as ViolationKey, count(*) as Occurrences
from {{ ref('PR_SST_Product_SellStart_Annex') }}
group by "PR_SST_ID", "PR_SST_Positor", "PR_SST_PositedAt"
having count(*) > 1
union all
select 'PR_SST_Product_SellStart_Annex', 'no row in PR_SST_Product_SellStart_Posit for PR_SST_ID', json_object('PR_SST_ID', c."PR_SST_ID"), count(*)
from {{ ref('PR_SST_Product_SellStart_Annex') }} c
left join {{ ref('PR_SST_Product_SellStart_Posit') }} p on p."PR_SST_ID" = c."PR_SST_ID"
where p."PR_SST_ID" is null
group by c."PR_SST_ID"
