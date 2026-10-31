-- The NUM key of every PR_Product identity over changing time: each value from its ChangedAt until the next. A key at a time T is the row with ChangedAt <= T < ChangedBefore.
{{ config(materialized='view') }}
select "PR_ID", "PR_NUM_Product_ProductNumber", changed_at as "ChangedAt",
    lead(changed_at, 1, cast('9999-12-31' as timestamp)) over (
        partition by "PR_ID" order by changed_at
    ) as "ChangedBefore"
from (
    select "PR_NUM_PR_ID" as "PR_ID", "PR_NUM_Product_ProductNumber", "PR_NUM_ChangedAt" as changed_at
    from {{ ref('PR_NUM_Product_ProductNumber') }}
    where "PR_NUM_Positor" = 0
    qualify row_number() over (partition by "PR_NUM_ID" order by "PR_NUM_PositedAt" desc) = 1
        and "PR_NUM_Reliable" = 1
)
