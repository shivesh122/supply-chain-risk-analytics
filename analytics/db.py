import sqlite3
from contextlib import closing

import pandas as pd

from pipeline.config import DB_PATH


def query(sql: str, params=(), db_path=DB_PATH) -> pd.DataFrame:
    with closing(sqlite3.connect(db_path)) as con:
        return pd.read_sql_query(sql, con, params=params)


def latest_date(db_path=DB_PATH) -> pd.Timestamp:
    df = query(
        "SELECT d.full_date FROM dim_date d WHERE d.date_key = (SELECT MAX(date_key) FROM fact_sales)", db_path=db_path
    )
    return pd.Timestamp(df.iloc[0, 0])
