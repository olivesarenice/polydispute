import json
import math
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import pandas as pd
import polars as pl
from config import PipelineConfig
from connectors.polymarket import ClobClient, PolyMarketPriceHistory
from db_utils import get_db_conn
from loguru import logger
from tqdm import tqdm
from utils.time_utils import TimeWindow, get_stage_output_path


def parse_unix_ts(val_str: Optional[str]) -> Optional[int]:
    """Converts an ISO8601 timestamp string to Unix timestamp in seconds."""
    if not val_str:
        return None
    try:
        dt = datetime.fromisoformat(str(val_str).replace("Z", "+00:00"))
        return int(dt.timestamp())
    except Exception:
        return None


def pull_dispute_price_history(
    window: TimeWindow,
    limit: Optional[int] = None,
    target_market_ids: Optional[List[str]] = None,
    targets: str = "unresolved",
    fidelity: int = 1,
    backfill_days: int = 14,
    max_threads: int = 8,
) -> str:
    """
    Phase 4 Pull: Multithreaded ingestion of midpoint price history for target markets.
    Saves binary Parquet payload to pipeline/data/raw/price_history/output_{runtime_unix}.parquet.
    """
    logger.info(
        f"Scanning MotherDuck for target disputed markets (targets={targets}, fidelity={fidelity}m, threads={max_threads})..."
    )
    conn = get_db_conn()

    status_filter = (
        "AND COALESCE(m.uma_resolution_status, '') != 'resolved'"
        if targets == "unresolved"
        else ""
    )

    limit_clause = f"LIMIT {int(limit)}" if (limit and limit > 0) else ""

    query = f"""
        SELECT 
            t.market_id,
            m.clob_token_ids,
            m.start_date,
            m.end_date,
            m.closed_time,
            m.uma_end_date,
            m.closed,
            m.uma_resolution_status,
            MAX(ph.observed_at) AS max_observed_at
        FROM clean_dc_threads t
        JOIN raw_pm_markets m ON t.market_id = m.id
        LEFT JOIN raw_pm_price_history ph ON t.market_id = ph.market_id
        WHERE t.market_id IS NOT NULL 
          AND t.market_id != ''
          AND LENGTH(t.market_id) >= 6
          AND m.clob_token_ids IS NOT NULL 
          AND m.clob_token_ids != ''
          {status_filter}
        GROUP BY 
            t.market_id, m.clob_token_ids, m.start_date, m.end_date, 
            m.closed_time, m.uma_end_date, m.closed, m.uma_resolution_status
        ORDER BY m.uma_end_date DESC
        {limit_clause}
    """

    try:
        df_targets = conn.execute(query).df()
    except Exception as e:
        logger.warning(f"Target market discovery query notice: {e}")
        fallback_sql = f"""
            SELECT 
                m.id AS market_id,
                m.clob_token_ids,
                m.start_date,
                m.end_date,
                m.closed_time,
                m.uma_end_date,
                m.closed,
                m.uma_resolution_status,
                MAX(ph.observed_at) AS max_observed_at
            FROM raw_pm_markets m
            LEFT JOIN raw_pm_price_history ph ON m.id = ph.market_id
            WHERE m.clob_token_ids IS NOT NULL 
              AND m.clob_token_ids != ''
              AND LENGTH(m.id) >= 6
              {status_filter}
            GROUP BY m.id, m.clob_token_ids, m.start_date, m.end_date, m.closed_time, m.uma_end_date, m.closed, m.uma_resolution_status
            {limit_clause}
        """
        df_targets = conn.execute(fallback_sql).df()
    finally:
        conn.close()

    out_file = get_stage_output_path("price_history", window.runtime_unix, "parquet")

    if df_targets.empty:
        logger.info("No target markets found for price history ingestion.")
        pl.DataFrame(schema={
            "market_id": pl.String,
            "yes_clob_token_id": pl.String,
            "yes_price": pl.Float64,
            "observed_at": pl.Int64,
            "observed_at_iso": pl.String,
        }).write_parquet(out_file)
        return out_file

    if target_market_ids:
        df_targets = df_targets[df_targets["market_id"].isin(target_market_ids)]

    prev_active_count = int((df_targets["max_observed_at"].notna()).sum())
    new_markets_count = int((df_targets["max_observed_at"].isna()).sum())

    logger.info(
        f"Target Price History Breakdown: {len(df_targets)} total target markets ({new_markets_count} completely new, {prev_active_count} previously active/existing)."
    )
    logger.info(
        f"Processing price history for {len(df_targets)} target markets (fidelity={fidelity}m, threads={max_threads})..."
    )
    clob_client = ClobClient()
    # Floor current timestamp to latest completed 60-second minute boundary
    now_ts = (int(datetime.now(timezone.utc).timestamp()) // 60) * 60

    tasks = []
    skipped_count = 0

    for _, row in df_targets.iterrows():
        m_id = str(row["market_id"])
        clob_raw = row["clob_token_ids"]
        max_obs = row["max_observed_at"]
        is_closed = bool(row["closed"]) if row["closed"] is not None else False

        try:
            tokens = json.loads(clob_raw) if isinstance(clob_raw, str) else clob_raw
            if not tokens or not isinstance(tokens, list):
                continue
            yes_token = str(tokens[0])
        except Exception:
            continue

        closed_ts = (
            parse_unix_ts(row.get("closed_time"))
            or parse_unix_ts(row.get("uma_end_date"))
            or parse_unix_ts(row.get("end_date"))
        )

        if closed_ts:
            closed_ts = (closed_ts // 60) * 60

        end_ts = closed_ts if (is_closed and closed_ts) else now_ts

        if pd.isna(max_obs):
            start_date_ts = parse_unix_ts(row.get("start_date"))
            lookback_cutoff = max(0, end_ts - (backfill_days * 86400))
            start_ts = (
                max(start_date_ts, lookback_cutoff)
                if start_date_ts
                else lookback_cutoff
            )
        else:
            max_obs_int = int(max_obs)
            if is_closed and closed_ts and max_obs_int >= closed_ts:
                skipped_count += 1
                continue
            start_ts = max_obs_int + 1

        if start_ts >= end_ts:
            skipped_count += 1
            continue

        tasks.append((m_id, yes_token, start_ts, end_ts))

    all_records: List[Dict[str, Any]] = []

    def fetch_market_history(task_item: tuple) -> List[Dict[str, Any]]:
        m_id, yes_token, start_ts, end_ts = task_item
        records = []
        try:
            history = clob_client.get_prices_history(
                token_id=yes_token,
                start_ts=start_ts,
                end_ts=end_ts,
                fidelity=fidelity,
            )

            if history:
                for pt in history:
                    if "p" in pt and "t" in pt:
                        obs_ts = int(pt["t"])
                        obs_iso = datetime.fromtimestamp(
                            obs_ts, tz=timezone.utc
                        ).strftime("%Y-%m-%dT%H:%M:%SZ")
                        record = PolyMarketPriceHistory(
                            market_id=m_id,
                            yes_clob_token_id=yes_token,
                            yes_price=float(pt["p"]),
                            observed_at=obs_ts,
                            observed_at_iso=obs_iso,
                        )
                        records.append(record.model_dump(by_alias=False))
        except Exception as e:
            logger.warning(f"Failed price history pull for token {yes_token} (market {m_id}): {e}")
        return records

    with ThreadPoolExecutor(max_workers=max_threads) as executor:
        futures = [executor.submit(fetch_market_history, task) for task in tasks]
        for f in tqdm(as_completed(futures), total=len(futures), desc="Pulling Price History (Parallel)"):
            res = f.result()
            if res:
                all_records.extend(res)

    if all_records:
        df_out = pl.DataFrame(all_records)
    else:
        df_out = pl.DataFrame(schema={
            "market_id": pl.String,
            "yes_clob_token_id": pl.String,
            "yes_price": pl.Float64,
            "observed_at": pl.Int64,
            "observed_at_iso": pl.String,
        })

    df_out.write_parquet(out_file, compression="zstd")

    logger.success(
        f"Phase 4 Pull Complete: Staged {len(all_records)} price bars across target markets to {out_file} (threads={max_threads}, skipped {skipped_count} settled/up-to-date markets)."
    )
    return out_file
