import json
import os
import re
from typing import Any, Dict, List, Optional

from config import PipelineConfig
from connectors.polymarket import PolymarketClient
from db_utils import get_db_conn
from loguru import logger
from utils.time_utils import (
    TimeWindow,
    get_latest_stage_file,
    get_stage_output_path,
)


def get_target_dispute_ids() -> List[str]:
    """
    Extracts distinct target dispute market IDs from clean_dc_threads or raw_dc_threads in MotherDuck.
    Selects newly discovered markets OR markets where closed = false AND uma_resolution_status != 'resolved'.
    """
    target_ids = set()

    # 1. Try querying MotherDuck clean_dc_threads joined with raw_pm_markets
    try:
        conn = get_db_conn()
        rows = conn.execute(
            """
            SELECT DISTINCT cdt.market_id 
            FROM clean_dc_threads cdt
            LEFT JOIN raw_pm_markets rpm ON cdt.market_id = rpm.id
            WHERE cdt.market_id IS NOT NULL 
              AND cdt.market_id != ''
              AND (
                rpm.id IS NULL 
                OR (rpm.closed = false AND COALESCE(rpm.uma_resolution_status, '') != 'resolved')
              )
            """
        ).fetchall()
        conn.close()
        for r in rows:
            val = str(r[0]).strip()
            # Ignore trailing 10-digit Unix timestamps (- 1785708038)
            if val.isdigit() and len(val) <= 8:
                target_ids.add(val)
    except Exception as e:
        logger.debug(f"MotherDuck clean_dc_threads query notice: {e}")

    # 2. Fallback: Parse latest staged raw/discord/output_<unix>.json
    if not target_ids:
        try:
            dc_file = get_latest_stage_file("discord")

            if os.path.exists(dc_file):
                with open(dc_file, "r") as f:
                    threads_payload = json.load(f)

                mid_pattern = re.compile(r"market_id:\s*(\d+)")
                for item in threads_payload:
                    content = item.get("content", "")
                    m = mid_pattern.search(content)
                    if m and len(m.group(1)) <= 8:
                        target_ids.add(m.group(1))

                    msgs = item.get("messages", [])
                    for msg in msgs:
                        m_msg = mid_pattern.search(msg.get("content", ""))
                        if m_msg and len(m_msg.group(1)) <= 8:
                            target_ids.add(m_msg.group(1))
        except Exception as e:
            logger.debug(f"Staged discord_threads.json fallback notice: {e}")

    logger.info(
        f"Extracted {len(target_ids)} distinct target dispute market IDs for Polymarket pull."
    )
    return list(target_ids)


def pull_polymarket_stage(window: TimeWindow, max_threads: int = 16) -> str:
    """
    Targeted Polymarket Pull: Fetches each target Polymarket market via singular
    GET /markets/{id} endpoint concurrently (max_threads=16) for all distinct
    market_ids extracted from Discord disputes.
    Saves payload to pipeline/data/raw/polymarket/output_{runtime_unix}.json.
    """
    out_file = get_stage_output_path("polymarket", window.runtime_unix, "json")
    logger.info(
        f"Targeted Market Pull: Ingesting Polymarket target markets for window {window} (max_threads={max_threads})..."
    )

    target_ids = get_target_dispute_ids()
    pm_client = PolymarketClient()

    raw_markets: List[Dict[str, Any]] = []

    if target_ids:
        fetched_markets = pm_client.get_markets_by_ids(
            target_ids, max_workers=max_threads
        )
        raw_markets = [m.model_dump(by_alias=False) for m in fetched_markets]

    with open(out_file, "w") as f:
        json.dump({"events": [], "markets": raw_markets}, f, indent=2)

    logger.success(
        f"Targeted Market Pull Complete: Saved {len(raw_markets)}/{len(target_ids)} target markets to {out_file} (threads={max_threads})"
    )
    return out_file
