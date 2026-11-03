-- The SID key of every PS_ProductSubcategory identity over changing time: each value from its ChangedAt until the next. A key at a time T is the row with ChangedAt <= T < ChangedBefore.
{{ config(materialized='view') }}
select "PS_ID", "PS_SID_ProductSubcategory_SourceId", changed_at as "ChangedAt",
    lead(changed_at, 1, cast('9999-12-31' as timestamp)) over (
        partition by "PS_ID" order by changed_at
    ) as "ChangedBefore"
from (
    select "PS_SID_PS_ID" as "PS_ID", "PS_SID_ProductSubcategory_SourceId", "PS_SID_ChangedAt" as changed_at
    from (
        {{ anchor_latest({'mnemonic': 'PS_SID', 'name': 'PS_SID_ProductSubcategory_SourceId'}) }}
    )
)
