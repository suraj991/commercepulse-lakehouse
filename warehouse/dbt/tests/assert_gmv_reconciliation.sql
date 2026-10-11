-- assert_gmv_reconciliation
--
-- Cross-checks fulfilled GMV between fct_orders and fct_order_items.
-- fct_orders computes GMV by aggregating order_items to order grain.
-- fct_order_items aggregates to (order_id, seller_id) grain.
-- Both should sum to the same per-order GMV for delivered orders.
-- Tolerance: ±0.01 BRL for decimal rounding.
-- Returns rows that violate the reconciliation; passes when 0 rows returned.
with
from_orders as (
    select
        order_id,
        gmv_brl as orders_gmv
    from {{ ref('fct_orders') }}
    where is_delivered = 1
),
from_items as (
    select
        order_id,
        sum(fulfilled_gmv_brl) as items_gmv
    from {{ ref('fct_order_items') }}
    group by order_id
)
select
    o.order_id,
    o.orders_gmv,
    coalesce(i.items_gmv, 0.0)                          as items_gmv,
    abs(o.orders_gmv - coalesce(i.items_gmv, 0.0))     as gap_brl
from from_orders o
left join from_items i using (order_id)
where abs(o.orders_gmv - coalesce(i.items_gmv, 0.0)) > 0.01
