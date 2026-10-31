-- Every integrity check of the model in one view: a row is something wrong.
{{ config(materialized='view') }}
select
    cast(null as varchar) as Construct,
    cast(null as varchar) as Violation,
    cast(null as json) as ViolationKey,
    cast(null as bigint) as Occurrences
where false
union all select * from {{ ref('ic_PR_Product') }}
union all select * from {{ ref('ic_PR_NUM_Product_ProductNumber_Posit') }}
union all select * from {{ ref('ic_PR_NUM_Product_ProductNumber_Annex') }}
union all select * from {{ ref('ic_PR_NUM_Product_ProductNumber') }}
union all select * from {{ ref('ic_PR_NAM_Product_Name_Posit') }}
union all select * from {{ ref('ic_PR_NAM_Product_Name_Annex') }}
union all select * from {{ ref('ic_PR_NAM_Product_Name') }}
union all select * from {{ ref('ic_PR_LIN_Product_ProductLine_Posit') }}
union all select * from {{ ref('ic_PR_LIN_Product_ProductLine_Annex') }}
union all select * from {{ ref('ic_PR_LIN_Product_ProductLine') }}
union all select * from {{ ref('ic_PR_COL_Product_Color_Posit') }}
union all select * from {{ ref('ic_PR_COL_Product_Color_Annex') }}
union all select * from {{ ref('ic_PR_COL_Product_Color') }}
union all select * from {{ ref('ic_PR_SST_Product_SellStart_Posit') }}
union all select * from {{ ref('ic_PR_SST_Product_SellStart_Annex') }}
union all select * from {{ ref('ic_PR_SST_Product_SellStart') }}
union all select * from {{ ref('ic_PR_SEN_Product_SellEnd_Posit') }}
union all select * from {{ ref('ic_PR_SEN_Product_SellEnd_Annex') }}
union all select * from {{ ref('ic_PR_SEN_Product_SellEnd') }}
union all select * from {{ ref('ic_PR_DIS_Product_Discontinued_Posit') }}
union all select * from {{ ref('ic_PR_DIS_Product_Discontinued_Annex') }}
union all select * from {{ ref('ic_PR_DIS_Product_Discontinued') }}
union all select * from {{ ref('ic_key_PR_Product_NUM') }}
-- hand edit for the story 2 red proof
