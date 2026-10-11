-- fct_payments: one row per order with payment reconciliation.
--
-- Metric: payment_reconciliation (see contracts/metrics.yml).
-- gap = total_payment_brl - total_item_brl (price + freight).
-- is_reconciled = |gap| <= 0.01 BRL (floating-point rounding tolerance).
-- gap != 0 for canceled orders is expected; reported but not a quality failure.
with
payments as (
    select * from {{ ref('int_payment_totals') }}
),
items as (
    select
        order_id,
        sum(price + freight_value)::decimal(14, 2) as total_item_brl
    from {{ ref('stg_order_items') }}
    group by order_id
),
orders as (
    select order_id, order_status from {{ ref('stg_orders') }}
)

select
    o.order_id,
    o.order_status,
    coalesce(p.total_payment_brl, 0.0)          as total_payment_brl,
    coalesce(i.total_item_brl,    0.0)          as total_item_brl,
    (
        coalesce(p.total_payment_brl, 0.0)
        - coalesce(i.total_item_brl,  0.0)
    )::decimal(14, 4)                           as payment_gap_brl,
    abs(
        coalesce(p.total_payment_brl, 0.0)
        - coalesce(i.total_item_brl,  0.0)
    ) <= 0.01                                   as is_reconciled,
    p.payment_row_count,
    p.distinct_payment_types,
    p.max_installments

from orders o
left join payments p using (order_id)
left join items    i using (order_id)
-- Only include orders that appear in at least payments or items
where p.order_id is not null
   or i.order_id is not null
