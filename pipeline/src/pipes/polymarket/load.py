import json
import os
from typing import Dict, Any, Optional

import polars as pl
from loguru import logger

from config import PipelineConfig
from db_utils import get_db_conn, load_json_to_table
from utils.time_utils import (
    TimeWindow,
    get_latest_stage_file,
    get_stage_output_path,
)


def load_polymarket_stage(window: Optional[TimeWindow | int] = None) -> None:
    """
    Phase 0 Load: Reads pipeline/data/raw/polymarket/output_{runtime_unix}.json
    and bulk loads raw_pm_markets into MotherDuck.
    If runtime_unix is not specified, loads from the latest available staging directory.
    """
    runtime_unix = window.runtime_unix if isinstance(window, TimeWindow) else (window if isinstance(window, int) else None)
    run_id = window.run_id if isinstance(window, TimeWindow) else None

    if runtime_unix:
        pm_file = get_stage_output_path("polymarket", runtime_unix, "json")
        if not os.path.exists(pm_file):
            pm_file = get_latest_stage_file("polymarket")
    else:
        pm_file = get_latest_stage_file("polymarket")

    if not os.path.exists(pm_file):
        logger.error(f"Phase 0 Load Error: File not found {pm_file}")
        raise FileNotFoundError(f"Polymarket staged file missing: {pm_file}")

    logger.info(f"Phase 0 Load: Ingesting Polymarket catalog from {pm_file} (runtime_unix={runtime_unix}) into MotherDuck...")

    with open(pm_file, "r") as f:
        data = json.load(f)

    markets = data.get("markets", [])

    if markets:
        load_json_to_table("raw_pm_markets", markets, pk="id", run_id=run_id)
        logger.info(f"Loaded {len(markets)} markets into raw_pm_markets")

    logger.success(f"Phase 0 Load Complete for runtime_unix={runtime_unix}")


def clean_polymarket_stage(
    run_id: Optional[str] = None,
    full_refresh: bool = False,
) -> None:
    """
    Phase 0 Clean: Transforms raw_pm_markets into Silver clean_pm_markets.
    Parses stringified JSON arrays (outcome_prices, clob_token_ids) into typed columns.

    Incremental optimization:
    - If run_id is supplied and not full_refresh, only transforms markets that:
      1) were touched in the current pipeline run (_source_run_id = run_id)
      2) were updated within the last 30 minutes
      3) are missing from clean_pm_markets
    - Otherwise processes all rows (full refresh fallback).
    """
    logger.info("Phase 0 Clean: Transforming raw_pm_markets into clean_pm_markets...")
    conn = get_db_conn()

    # Check if clean_pm_markets exists to safely execute incremental LEFT JOIN
    table_exists = False
    try:
        res = conn.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_name = 'clean_pm_markets'"
        ).fetchone()
        table_exists = res is not None
    except Exception:
        table_exists = False

    base_cols = """
        r.id AS market_id,
        r.question,
        r.description,
        r.condition_id,
        r.slug,
        r.resolution_source,
        r.closed,
        r.active,
        r.category,
        r.outcome_prices,
        r.clob_token_ids,
        r.start_date,
        r.end_date,
        r.closed_time,
        r.uma_end_date,
        r.uma_resolution_status,
        r.uma_question_id,
        r.resolved_by
    """

    if not full_refresh and run_id and table_exists:
        query = f"""
        SELECT {base_cols}
        FROM raw_pm_markets r
        LEFT JOIN clean_pm_markets c ON r.id = c.market_id
        WHERE c.market_id IS NULL
           OR r._source_run_id = '{run_id}'
           OR r._updated_at >= now() - INTERVAL '30 minutes'
        """
        logger.info(f"Phase 0 Clean: Performing incremental transform for run_id={run_id}...")
    else:
        query = """
        SELECT 
            id AS market_id,
            question,
            description,
            condition_id,
            slug,
            resolution_source,
            closed,
            active,
            category,
            outcome_prices,
            clob_token_ids,
            start_date,
            end_date,
            closed_time,
            uma_end_date,
            uma_resolution_status,
            uma_question_id,
            resolved_by
        FROM raw_pm_markets
        """
        logger.info("Phase 0 Clean: Performing full catalog transform on raw_pm_markets...")

    df = conn.execute(query).pl()
    conn.close()

    if not df.is_empty():
        def parse_yes_price(prices_str: Optional[str]) -> Optional[float]:
            if not prices_str:
                return None
            try:
                p_list = json.loads(prices_str) if isinstance(prices_str, str) else prices_str
                if isinstance(p_list, list) and len(p_list) > 0:
                    return float(p_list[0])
            except Exception:
                pass
            return None

        def parse_no_price(prices_str: Optional[str]) -> Optional[float]:
            if not prices_str:
                return None
            try:
                p_list = json.loads(prices_str) if isinstance(prices_str, str) else prices_str
                if isinstance(p_list, list) and len(p_list) > 1:
                    return float(p_list[1])
            except Exception:
                pass
            return None

        yes_prices = [parse_yes_price(p) for p in df["outcome_prices"]]
        no_prices = [parse_no_price(p) for p in df["outcome_prices"]]

        df_clean = df.with_columns(
            pl.Series("yes_price", yes_prices, dtype=pl.Float64),
            pl.Series("no_price", no_prices, dtype=pl.Float64),
        ).drop("outcome_prices")

        records = df_clean.to_dicts()
        load_json_to_table("clean_pm_markets", records, pk="market_id", run_id=run_id)
        logger.info(f"Loaded {len(records)} records into clean_pm_markets")
    else:
        logger.info("Phase 0 Clean: No new or modified markets to transform.")

    logger.success("Phase 0 Clean Complete.")
