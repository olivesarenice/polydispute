import json
import os
from typing import Optional

import polars as pl
from loguru import logger

from config import PipelineConfig
from db_utils import get_db_conn, load_json_to_table
from utils.time_utils import (
    TimeWindow,
    get_latest_stage_file,
    get_stage_output_path,
)


def load_uma_rocks_stage(window: Optional[TimeWindow | int] = None) -> None:
    """
    Phase 3 Load: Reads pipeline/data/raw/umarocks/output_{runtime_unix}.json,
    bulk loads raw_ur_signals into MotherDuck, and transforms clean_ur_signals.
    """
    runtime_unix = window.runtime_unix if isinstance(window, TimeWindow) else (window if isinstance(window, int) else None)
    run_id = window.run_id if isinstance(window, TimeWindow) else None

    if runtime_unix:
        uma_file = get_stage_output_path("umarocks", runtime_unix, "json")
        if not os.path.exists(uma_file):
            uma_file = get_latest_stage_file("umarocks")
    else:
        uma_file = get_latest_stage_file("umarocks")

    if not os.path.exists(uma_file):
        logger.error(f"Phase 3 Load Error: File not found {uma_file}")
        raise FileNotFoundError(f"UMA Rocks staged file missing: {uma_file}")

    logger.info(f"Phase 3 Load: Ingesting UMA Rocks signals from {uma_file} (runtime_unix={runtime_unix}) into MotherDuck...")

    with open(uma_file, "r") as f:
        records = json.load(f)

    if records:
        load_json_to_table("raw_ur_signals", records, pk="id", on_conflict="ignore", run_id=run_id)
        logger.info(f"Loaded {len(records)} records into raw_ur_signals")

    clean_uma_rocks_stage(run_id=run_id)
    logger.success(f"Phase 3 Load Complete for runtime_unix={runtime_unix}")


def clean_uma_rocks_stage(run_id: Optional[str] = None) -> None:
    """
    Transforms raw_ur_signals into Silver clean_ur_signals.
    """
    logger.info("Phase 3 Clean: Transforming raw_ur_signals into clean_ur_signals...")
    conn = get_db_conn()
    try:
        df_ur = conn.execute("SELECT id, question, ancillary_data, answer, round_id, timestamp, timestamp_iso FROM raw_ur_signals").pl()
        conn.close()
        if not df_ur.is_empty():
            load_json_to_table("clean_ur_signals", df_ur.to_dicts(), pk="id", run_id=run_id)
            logger.info(f"Loaded {len(df_ur)} records into clean_ur_signals")
    except Exception as e:
        logger.warning(f"clean_ur_signals transformation notice: {e}")
        conn.close()

    logger.success("Phase 3 Clean Complete.")
