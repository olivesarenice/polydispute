import json
import os
from typing import Optional

import polars as pl
from config import PipelineConfig
from db_utils import load_json_to_table
from loguru import logger
from utils.time_utils import (
    TimeWindow,
    get_latest_stage_file,
    get_stage_output_path,
)


def load_price_history_stage(window: Optional[TimeWindow | int] = None) -> None:
    """
    Phase 4 Load: Reads pipeline/data/raw/price_history/output_{runtime_unix}.parquet (or .json)
    and bulk loads raw_pm_price_history into MotherDuck.
    """
    runtime_unix = window.runtime_unix if isinstance(window, TimeWindow) else (window if isinstance(window, int) else None)
    run_id = window.run_id if isinstance(window, TimeWindow) else None

    if runtime_unix:
        ph_file = get_stage_output_path("price_history", runtime_unix, "parquet")
        if not os.path.exists(ph_file):
            ph_file = get_latest_stage_file("price_history")
    else:
        ph_file = get_latest_stage_file("price_history")

    if not os.path.exists(ph_file):
        logger.error(f"Phase 4 Load Error: File not found {ph_file}")
        raise FileNotFoundError(f"Price history staged file missing: {ph_file}")

    records = []
    if ph_file.endswith(".parquet"):
        logger.info(f"Phase 4 Load: Ingesting Parquet price history from {ph_file} into MotherDuck...")
        df = pl.read_parquet(ph_file)
        if not df.is_empty():
            records = df.to_dicts()
    elif ph_file.endswith(".json"):
        logger.info(f"Phase 4 Load: Ingesting JSON price history from {ph_file} into MotherDuck...")
        with open(ph_file, "r") as f:
            records = json.load(f)
    else:
        logger.error(f"Phase 4 Load Error: Unsupported file format {ph_file}")
        raise ValueError(f"Unsupported file format: {ph_file}")

    if records:
        load_json_to_table(
            "raw_pm_price_history",
            records,
            pk="market_id, observed_at",
            on_conflict="ignore",
            run_id=run_id,
        )
        logger.info(f"Loaded {len(records)} records into raw_pm_price_history")

    logger.success(f"Phase 4 Load Complete for runtime_unix={runtime_unix}")
