select
    order_id,
    payment_sequential,
    payment_type,
    payment_installments,
    payment_value::decimal(12, 2)   as payment_value
from read_parquet('{{ var("gold_input_dir") }}/order_payments/*/data.parquet')
