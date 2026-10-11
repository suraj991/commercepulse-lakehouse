-- assert_scd2_no_overlap
--
-- Verifies that no seller has overlapping validity periods in dim_seller_history.
-- Overlapping records cause fan-out when joining on:
--   seller_id = s.seller_id AND order_date BETWEEN s.valid_from AND s.valid_to
-- Returns pairs of overlapping records; passes when 0 rows returned.
select
    a.seller_id,
    a.seller_sk     as sk_a,
    b.seller_sk     as sk_b,
    a.valid_from    as a_valid_from,
    a.valid_to      as a_valid_to,
    b.valid_from    as b_valid_from,
    b.valid_to      as b_valid_to
from {{ ref('dim_seller_history') }} a
join {{ ref('dim_seller_history') }} b
    on  a.seller_id  = b.seller_id
    and a.seller_sk != b.seller_sk
    and a.valid_from  < b.valid_to
    and a.valid_to    > b.valid_from
