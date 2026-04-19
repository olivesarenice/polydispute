import sqlite3

import pandas as pd

data_paths = {
    "dc_messages": "data/discord/1776096570/_messages.parquet",
    "dc_threads": "data/discord/1776096570/_threads.parquet",
    "pm_events": "data/1775970891/_events_99999999.parquet",
    "pm_markets": "data/1775970891/_markets_99999999.parquet",
}

db_conn = sqlite3.connect(database="data/polydispute.db")
for table_name, parquet_path in data_paths.items():
    df_parquet = pd.read_parquet(parquet_path)
    num_rows_inserted = df_parquet.to_sql(table_name, db_conn, index=False)
    query = f"SELECT * from {table_name} limit 10"
    cursor = db_conn.execute(query)
    print(cursor.fetchall())
