import json
import sqlite3
from typing import List, Dict, Any
from loguru import logger

from config import PipelineConfig


def get_sqlite_conn() -> sqlite3.Connection:
    return sqlite3.connect(PipelineConfig.DB_PATH)


def load_json_to_table(table: str, records: List[Dict[str, Any]], pk: str = "id") -> None:
    if not records:
        return
        
    conn = get_sqlite_conn()
    cursor = conn.cursor()
    
    columns = list(records[0].keys())
    placeholders = ",".join(["?"] * len(columns))
    col_str = ",".join(columns)
    
    updates = ",".join([f"{c}=excluded.{c}" for c in columns if c != pk])
    insert_sql = f"""
        INSERT INTO {table} ({col_str})
        VALUES ({placeholders})
        ON CONFLICT({pk}) DO UPDATE SET
            _updated_at=CURRENT_TIMESTAMP,
            {updates}
    """
    
    data_tuples = []
    for r in records:
        row = []
        for c in columns:
            val = r.get(c)
            if isinstance(val, (dict, list)):
                val = json.dumps(val)
            row.append(val)
        data_tuples.append(tuple(row))
        
    try:
        cursor.executemany(insert_sql, data_tuples)
        conn.commit()
    except Exception as e:
        logger.error(f"Failed to bulk insert into {table}: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()
