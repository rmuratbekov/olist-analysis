from pathlib import Path

import duckdb

FILES = {
    "orders": "olist_orders_dataset.csv",
    "order_items": "olist_order_items_dataset.csv",
    "products": "olist_products_dataset.csv",
    "customers": "olist_customers_dataset.csv",
    "reviews": "olist_order_reviews_dataset.csv",
}


def connect(data_dir="data/raw"):
    # in-memory database, one view per csv (views read the file, nothing is copied)
    raw = Path(data_dir)
    con = duckdb.connect()

    for view, file in FILES.items():
        path = (raw / file).as_posix()
        con.sql(f"CREATE VIEW {view} AS SELECT * FROM read_csv_auto('{path}')")

    # the translation file starts with a BOM, so I set the column names myself
    path = (raw / "product_category_name_translation.csv").as_posix()
    con.sql(f"""
        CREATE VIEW category_translation AS
        SELECT * FROM read_csv_auto('{path}', header = true,
            names = ['product_category_name', 'product_category_name_english'])
    """)
    return con
