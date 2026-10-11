-- Aggregate order items to (order_id, seller_id) grain.
--
-- Fan-out prevention: joining dim_seller_history at the raw item grain would
-- multiply each item row if a seller had more than one SCD2 record in scope.
-- Aggregating first ensures one row per (order_id, seller_id) before any dim join.
select
    order_id,
    seller_id,
    count(*)                                    as item_count,
    sum(price)::decimal(14, 2)                  as total_price_brl,
    sum(freight_value)::decimal(14, 2)          as total_freight_brl,
    sum(price + freight_value)::decimal(14, 2)  as total_value_brl,
    min(shipping_limit_date)                    as earliest_shipping_limit
from {{ ref('stg_order_items') }}
group by order_id, seller_id
