-- assert_no_fanout_order_items
--
-- Verifies that fct_order_items has at most one row per (order_id, seller_id).
-- Duplicates here mean the dim_seller_history join caused fan-out — every seller
-- had more than one SCD2 record active at the order's purchase date.
-- Returns rows that violate uniqueness; the test passes when this query returns 0 rows.
select
    order_id,
    seller_id,
    count(*) as row_count
from {{ ref('fct_order_items') }}
group by order_id, seller_id
having count(*) > 1
