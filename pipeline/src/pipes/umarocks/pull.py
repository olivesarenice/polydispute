import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List

from config import PipelineConfig
from connectors.uma_rocks import UMARocksClient
from db_utils import get_db_conn
from loguru import logger
from tqdm import tqdm
from utils.time_utils import TimeWindow, get_stage_output_path


def pull_uma_rocks_signals(window: TimeWindow) -> str:
    """
    Phase 3 Pull: Pulls UMA Rocks committee consensus signals from getPoolAnswers API.
    Uses MAX(timestamp) from raw_ur_signals to only pull new records incrementally.
    Saves payload to pipeline/data/raw/umarocks/output_{runtime_unix}.json.
    """
    logger.info("Checking MotherDuck for latest UMA Rocks timestamp watermark...")
    conn = get_db_conn()
    max_ts = 0
    try:
        row = conn.execute("SELECT MAX(timestamp) FROM raw_ur_signals").fetchone()
        if row and row[0] is not None:
            max_ts = int(row[0])
    except Exception as e:
        logger.debug(f"raw_ur_signals watermark query notice: {e}")
    finally:
        conn.close()

    logger.info(f"Existing UMA Rocks MAX(timestamp) = {max_ts}")

    client = UMARocksClient()
    raw_signals = client.get_pool_answers()

    out_file = get_stage_output_path("umarocks", window.runtime_unix, "json")

    if not raw_signals:
        logger.info("No signals returned from UMA Rocks API.")
        with open(out_file, "w") as f:
            json.dump([], f)
        return out_file

    records: List[Dict[str, Any]] = []

    for item in tqdm(raw_signals, desc="Parsing UMA Rocks signals"):
        ts = int(item.get("timestamp") or item.get("time") or 0)

        if max_ts > 0 and ts <= max_ts:
            continue

        ancillary = item.get("ancillaryData") or item.get("ancillary_data") or ""
        round_id = int(item.get("roundId") or item.get("round_id") or 0)
        synth_id = hashlib.sha256(f"{round_id}_{ancillary}_{ts}".encode()).hexdigest()[:16]

        ts_iso = (
            datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            if ts
            else None
        )

        record = {
            "id": item.get("id", synth_id),
            "question": item.get("question"),
            "ancillary_data": ancillary,
            "answer": item.get("answer"),
            "round_id": round_id,
            "timestamp": ts,
            "timestamp_iso": ts_iso,
        }
        records.append(record)

    with open(out_file, "w") as f:
        json.dump(records, f, indent=2)

    logger.success(f"Phase 3 Pull Complete: Staged {len(records)} UMA Rocks signals to {out_file}")
    return out_file
