select
    seller_id,
    seller_zip_code_prefix,
    seller_city,
    seller_state
from read_parquet('{{ var("gold_input_dir") }}/sellers/*/data.parquet')
