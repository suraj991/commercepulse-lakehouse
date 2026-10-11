select
    product_category_name,
    product_category_name_english
from read_parquet('{{ var("gold_input_dir") }}/product_category_translations/*/data.parquet')
