select
    order_id,
    order_item_id,
    product_id,
    seller_id,
    shipping_limit_date::timestamp  as shipping_limit_date,
    price::decimal(12, 2)           as price,
    freight_value::decimal(12, 2)   as freight_value
from read_parquet('{{ var("gold_input_dir") }}/order_items/*/data.parquet')
