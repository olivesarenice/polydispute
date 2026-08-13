import json
import os
import re
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


def load_discord_stage(window: Optional[TimeWindow | int] = None) -> None:
    """
    Phase 1 Load: Reads pipeline/data/raw/discord/output_{runtime_unix}.json,
    bulk loads raw_dc_threads & raw_dc_messages, and automatically transforms clean_dc_threads & clean_dc_messages.
    """
    runtime_unix = window.runtime_unix if isinstance(window, TimeWindow) else (window if isinstance(window, int) else None)
    run_id = window.run_id if isinstance(window, TimeWindow) else None

    if runtime_unix:
        dc_file = get_stage_output_path("discord", runtime_unix, "json")
        if not os.path.exists(dc_file):
            dc_file = get_latest_stage_file("discord")
    else:
        dc_file = get_latest_stage_file("discord")

    if not os.path.exists(dc_file):
        logger.error(f"Phase 1 Load Error: File not found {dc_file}")
        raise FileNotFoundError(f"Discord staged file missing: {dc_file}")

    logger.info(f"Phase 1 Load: Ingesting Discord data from {dc_file} (runtime_unix={runtime_unix}) into MotherDuck...")

    with open(dc_file, "r") as f:
        threads_payload = json.load(f)

    threads = []
    messages = []

    for item in threads_payload:
        t_data = dict(item)
        m_list = t_data.pop("messages", [])

        if isinstance(t_data.get("thread_metadata"), (dict, list)):
            t_data["thread_metadata"] = json.dumps(t_data["thread_metadata"])
        if isinstance(t_data.get("embeds"), (dict, list)):
            t_data["embeds"] = json.dumps(t_data["embeds"])

        threads.append(t_data)

        if m_list:
            for msg in m_list:
                msg_dict = dict(msg)
                if isinstance(msg_dict.get("embeds"), (dict, list)):
                    msg_dict["embeds"] = json.dumps(msg_dict["embeds"])
                messages.append(msg_dict)

    if threads:
        load_json_to_table("raw_dc_threads", threads, pk="id", run_id=run_id)
        logger.info(f"Loaded {len(threads)} threads into raw_dc_threads")

    if messages:
        load_json_to_table("raw_dc_messages", messages, pk="id", run_id=run_id)
        logger.info(f"Loaded {len(messages)} messages into raw_dc_messages")

    # Automatically transform & extract market_id into clean_dc_threads during load
    clean_discord_stage(run_id=run_id)

    logger.success(f"Phase 1 Load Complete for runtime_unix={runtime_unix}")


def clean_discord_stage(run_id: Optional[str] = None) -> None:
    """
    Phase 1 Clean: Transforms raw_dc_threads into clean_dc_threads (market_id FK)
    and raw_dc_messages into clean_dc_messages (vote stance).
    Supports market_id: \\d+ pattern matching + fallback slug lookup against raw_pm_markets.
    """
    logger.info("Phase 1 Clean: Transforming raw_dc_threads into clean_dc_threads...")
    conn = get_db_conn()

    # Pre-build slug-to-market_id map from raw_pm_markets for fallback resolution
    slug_to_mid = {}
    try:
        slug_rows = conn.execute("SELECT slug, id FROM raw_pm_markets WHERE slug IS NOT NULL AND slug != ''").fetchall()
        slug_to_mid = {r[0]: r[1] for r in slug_rows}
    except Exception as e:
        logger.debug(f"Slug-to-market_id map build notice: {e}")

    query_threads = "SELECT id as thread_id, author_username, timestamp, content FROM raw_dc_threads"
    query_messages = "SELECT thread_id, content FROM raw_dc_messages WHERE content LIKE '%market_id:%' OR content LIKE '%polymarket.com%'"

    df_threads = conn.execute(query_threads).pl()
    df_msgs = conn.execute(query_messages).pl()
    conn.close()

    if not df_threads.is_empty():
        mid_mapping = {}
        market_id_pattern = re.compile(r"market_id:\s*(\d+)")
        slug_pattern = re.compile(r"polymarket\.com/(?:event|market)/([a-zA-Z0-9_-]+)")

        def resolve_mid_from_text(text: str) -> Optional[str]:
            if not text:
                return None
            m_match = market_id_pattern.search(text)
            if m_match:
                mid_str = m_match.group(1)
                if 6 <= len(mid_str) <= 8:
                    return mid_str
            s_match = slug_pattern.search(text)
            if s_match:
                slug = s_match.group(1)
                return slug_to_mid.get(slug)
            return None

        for row in df_msgs.to_dicts():
            t_id = row["thread_id"]
            if t_id in mid_mapping:
                continue
            res_mid = resolve_mid_from_text(row.get("content", ""))
            if res_mid:
                mid_mapping[t_id] = res_mid

        for row in df_threads.to_dicts():
            t_id = row["thread_id"]
            if t_id not in mid_mapping:
                res_mid = resolve_mid_from_text(row.get("content", ""))
                if res_mid:
                    mid_mapping[t_id] = res_mid

        mid_df = pl.DataFrame(
            {
                "thread_id": list(mid_mapping.keys()),
                "market_id": list(mid_mapping.values()),
            },
            schema={"thread_id": pl.String, "market_id": pl.String},
        )

        if not mid_df.is_empty():
            df_threads = df_threads.join(mid_df, on="thread_id", how="left")
        else:
            df_threads = df_threads.with_columns(
                pl.lit(None, dtype=pl.String).alias("market_id")
            )

        linked_count = df_threads.filter(pl.col("market_id").is_not_null()).height
        total_count = len(df_threads)
        logger.info(f"clean_dc_threads FK market_id coverage: {linked_count}/{total_count} linked.")

        records_t = df_threads.to_dicts()
        load_json_to_table("clean_dc_threads", records_t, pk="thread_id", run_id=run_id)
        logger.info(f"Loaded {len(records_t)} records into clean_dc_threads")

    logger.info("Phase 1 Clean: Transforming raw_dc_messages into clean_dc_messages...")
    query_m = "SELECT id as message_id, thread_id, author_username, timestamp, content FROM raw_dc_messages"
    conn = get_db_conn()
    df_m = conn.execute(query_m).pl()
    conn.close()

    if not df_m.is_empty():
        df_m = df_m.with_columns(
            pl.col("content")
            .str.extract(r"(?i)\b(P[1-4])\b", 1)
            .str.to_uppercase()
            .alias("vote_type")
        )
        df_votes = df_m.filter(pl.col("vote_type").is_not_null()).drop("content")
        if not df_votes.is_empty():
            records_m = df_votes.to_dicts()
            load_json_to_table("clean_dc_messages", records_m, pk="message_id", run_id=run_id)
            logger.info(f"Loaded {len(records_m)} records into clean_dc_messages")

    logger.success("Phase 1 Clean Complete.")
