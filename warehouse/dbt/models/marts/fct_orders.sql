-- fct_orders: one row per order.
--
-- Metric: fulfilled_gmv = sum(item.price) for delivered orders (see contracts/metrics.yml).
-- Freight is excluded from GMV by definition.
-- FX conversion: uses the latest cached BRL→USD rate on or before the order date.
-- gmv_usd is NULL when no rate is available (run `make backfill-fx`).
with
orders as (
    select * from {{ ref('stg_orders') }}
),
items_per_order as (
    -- Aggregate to order grain first — prevents fan-out when joining customers.
    select
        order_id,
        count(*)                            as item_count,
        sum(price)::decimal(14, 2)          as gmv_brl,
        sum(freight_value)::decimal(14, 2)  as freight_brl
    from {{ ref('stg_order_items') }}
    group by order_id
),
customers as (
    select customer_id, customer_state
    from {{ ref('stg_customers') }}
)

select
    o.order_id,
    o.customer_id,
    c.customer_state,
    o.order_status,
    o.order_purchase_timestamp,
    o.order_delivered_customer_date,
    o.order_estimated_delivery_date,

    -- Date grain columns for time-series aggregations
    date_trunc('day',   o.order_purchase_timestamp)::date   as order_date,
    date_trunc('month', o.order_purchase_timestamp)::date   as order_month,

    coalesce(i.item_count,  0)   as item_count,
    coalesce(i.gmv_brl,     0.0) as gmv_brl,
    coalesce(i.freight_brl, 0.0) as freight_brl,

    -- FX: latest rate on or before order_date via LATERAL
    fx.brl_to_usd,
    case
        when fx.brl_to_usd is not null
        then (coalesce(i.gmv_brl, 0.0) * fx.brl_to_usd)::decimal(14, 4)
    end as gmv_usd,

    -- Delivery status flags
    case
        when o.order_status = 'delivered'
             and o.order_delivered_customer_date is not null
        then 1 else 0
    end as is_delivered,

    case
        when o.order_delivered_customer_date > o.order_estimated_delivery_date
        then 1 else 0
    end as is_late_delivery

from orders o
left join items_per_order i using (order_id)
left join customers       c using (customer_id)
left join lateral (
    select brl_to_usd
    from {{ ref('dim_fx_rate') }}
    where rate_date <= date_trunc('day', o.order_purchase_timestamp)::date
    order by rate_date desc
    limit 1
) as fx on true
