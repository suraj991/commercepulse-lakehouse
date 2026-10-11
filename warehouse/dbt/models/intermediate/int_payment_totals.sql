-- Aggregate payments to order grain for reconciliation.
-- A single order can have multiple payment rows (installments, mixed methods).
select
    order_id,
    count(*)                                    as payment_row_count,
    sum(payment_value)::decimal(14, 2)          as total_payment_brl,
    count(distinct payment_type)                as distinct_payment_types,
    max(payment_installments)                   as max_installments
from {{ ref('stg_order_payments') }}
group by order_id
