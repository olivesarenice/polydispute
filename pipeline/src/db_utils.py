import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import duckdb
import pyarrow as pa
from loguru import logger


def get_db_conn(db_name: Optional[str] = None) -> duckdb.DuckDBPyConnection:
    """
    Establish a connection to the MotherDuck cloud database.
    Environment selection:
      - Uses PIPELINE_ENV ("dev" or "prod") to select polydispute_dev or polydispute_prod.
      - Can be explicitly overridden with MOTHERDUCK_DATABASE or db_name parameter.
    Automatically creates the target database in MotherDuck if it does not exist.
    """
    token = os.getenv("MOTHERDUCK_TOKEN")
    if not token or token.startswith("md_..."):
        raise ValueError(
            "MOTHERDUCK_TOKEN environment variable is required to connect to MotherDuck."
        )

    if not db_name:
        env = os.getenv("PIPELINE_ENV", "dev").strip().lower()
        db_name = os.getenv("MOTHERDUCK_DATABASE", f"polydispute_{env}")

    logger.debug(f"Connecting to MotherDuck cloud database '{db_name}'...")

    try:
        conn = duckdb.connect(f"md:?token={token}")
        conn.execute(f"CREATE DATABASE IF NOT EXISTS {db_name}")
        conn.execute(f"USE {db_name}")
        return conn
    except Exception as e:
        logger.error(
            f"Failed to connect/initialize MotherDuck database '{db_name}': {e}"
        )
        raise


def load_json_to_table(
    table: str,
    records: List[Dict[str, Any]],
    pk: str = "id",
    run_id: Optional[str] = None,
    conn: Optional[duckdb.DuckDBPyConnection] = None,
    on_conflict: str = "update",
) -> None:
    """
    Bulk load a list of dictionaries into a MotherDuck / DuckDB table.
    - on_conflict="update": Enforces ON CONFLICT ({pk}) DO UPDATE SET
    - on_conflict="ignore": Enforces ON CONFLICT ({pk}) DO NOTHING (append-only ignore existing)
    Automatically populates DW lineage columns (_source_table, _source_run_id, _run_created_at).
    """
    if not records:
        return

    should_close = False
    if conn is None:
        conn = get_db_conn()
        should_close = True

    default_run_id = run_id or os.getenv("EXECUTION_ID") or os.getenv("RUN_ID") or "batch_local"
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    # Serialize nested dicts/lists to JSON strings for standard VARCHAR storage
    # and supply default lineage tracking metadata
    cleaned_records = []
    for r in records:
        cleaned = {}
        for k, v in r.items():
            if isinstance(v, (dict, list)) and k != "_source_table":
                cleaned[k] = json.dumps(v)
            else:
                cleaned[k] = v

        if "_source_table" not in cleaned:
            cleaned["_source_table"] = [f"api:{table}"]
        if "_source_run_id" not in cleaned:
            cleaned["_source_run_id"] = default_run_id
        if "_run_created_at" not in cleaned:
            cleaned["_run_created_at"] = now_iso

        cleaned_records.append(cleaned)

    arrow_table = pa.Table.from_pylist(cleaned_records)

    columns = list(cleaned_records[0].keys())
    pk_cols = [p.strip() for p in pk.split(",")]
    pk_str = ", ".join(pk_cols)

    if on_conflict.lower() == "ignore":
        upsert_sql = f"""
            INSERT INTO {table}
            BY NAME
            SELECT * FROM arrow_table
            ON CONFLICT ({pk_str}) DO NOTHING
        """
    else:
        # Build UPDATE assignments for non-PK columns
        update_cols = [
            c for c in columns if c not in pk_cols and not c.startswith("_created")
        ]
        update_assignments = [f"{c} = EXCLUDED.{c}" for c in update_cols]
        update_assignments.append("_updated_at = now()")
        update_str = ", ".join(update_assignments)

        upsert_sql = f"""
            INSERT INTO {table}
            BY NAME
            SELECT * FROM arrow_table
            ON CONFLICT ({pk_str}) DO UPDATE SET
                {update_str}
        """

    try:
        conn.execute(upsert_sql)
        logger.debug(f"Successfully loaded {len(records)} records into {table} (on_conflict={on_conflict})")
    except Exception as e:
        logger.error(f"Failed to bulk upsert into {table}: {e}")
        raise
    finally:
        if should_close:
            conn.close()
