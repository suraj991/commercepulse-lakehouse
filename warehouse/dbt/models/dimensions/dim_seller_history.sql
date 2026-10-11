-- SCD Type 2 seller dimension.
--
-- The Olist dataset is a historical snapshot with no change events, so each
-- seller has exactly one record with a full-history validity window.
-- The SCD2 structure (valid_from / valid_to / is_current / surrogate key)
-- is production-ready: when a real change feed is introduced, additional rows
-- per seller_id are inserted with narrower date ranges without breaking joins.
--
-- Surrogate key: md5(seller_id) — stable across pipeline runs.
select
    md5(seller_id)          as seller_sk,
    seller_id,
    seller_zip_code_prefix,
    seller_city,
    seller_state,
    '2000-01-01'::date      as valid_from,
    '9999-12-31'::date      as valid_to,
    true                    as is_current
from {{ ref('stg_sellers') }}
