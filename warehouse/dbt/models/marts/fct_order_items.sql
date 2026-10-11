-- fct_order_items: one row per (order_id, seller_id).
--
-- Metrics: seller_gmv_attribution, observed_demand (see contracts/metrics.yml).
-- Fan-out prevention: int_order_items_agg pre-aggregates to (order_id, seller_id)
-- grain BEFORE joining dim_seller_history. Without this, a seller with N SCD2
-- records in range would multiply each item row by N.
with
agg as (
    select * from {{ ref('int_order_items_agg') }}
),
orders as (
    select
        order_id,
        order_status,
        order_purchase_timestamp,
        date_trunc('day', order_purchase_timestamp)::date   as order_date,
        order_delivered_customer_date,
        order_estimated_delivery_date
    from {{ ref('stg_orders') }}
),
products as (
{% if target.type == 'snowflake' %}
    -- Snowflake: mode via QUALIFY + ROW_NUMBER (MODE WITHIN GROUP not supported)
    select
        order_id,
        product_id as primary_product_id
    from {{ ref('stg_order_items') }}
    group by order_id, product_id
    qualify row_number() over (partition by order_id order by count(*) desc, product_id asc) = 1
{% else %}
    select
        order_id,
        -- Most common product category in this order+seller combination
        -- (for demand analysis; full item-level is in stg_order_items)
        mode() within group (order by product_id) as primary_product_id
    from {{ ref('stg_order_items') }}
    group by order_id
{% endif %}
),
sellers as (
    select * from {{ ref('dim_seller_history') }}
)

select
    a.order_id,
    a.seller_id,
    o.order_status,
    o.order_purchase_timestamp,
    o.order_date,
    o.order_delivered_customer_date,
    a.item_count,
    a.total_price_brl,
    a.total_freight_brl,
    a.earliest_shipping_limit,

    -- Seller dimension (SCD2 join at order purchase date)
    s.seller_sk,
    s.seller_zip_code_prefix,
    s.seller_city,
    s.seller_state,

    -- GMV attribution: seller gets credit only for their items, delivered only
    case
        when o.order_status = 'delivered'
        then a.total_price_brl
        else 0.0
    end::decimal(14, 2)     as fulfilled_gmv_brl,

    p.primary_product_id,

    -- Demand flags
    case when o.order_status = 'canceled' then 1 else 0 end as is_canceled,

    case
        when o.order_delivered_customer_date > o.order_estimated_delivery_date
        then 1 else 0
    end                     as is_late_delivery

from agg a
join orders o using (order_id)
left join products p using (order_id)
-- SCD2 join: seller attributes valid at time of order
left join sellers s
    on  a.seller_id  = s.seller_id
    and o.order_date between s.valid_from and s.valid_to
