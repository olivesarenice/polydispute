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
        load_json_to_table("raw_dc_messages", messages, pk="id", run_id=run_id, on_conflict="ignore")
        logger.info(f"Loaded {len(messages)} messages into raw_dc_messages")

    # Automatically transform & extract market_id into clean_dc_threads during load
    clean_discord_stage(run_id=run_id)

    logger.success(f"Phase 1 Load Complete for runtime_unix={runtime_unix}")


def clean_discord_stage(
    run_id: Optional[str] = None,
    full_refresh: bool = False,
) -> None:
    """
    Phase 1 Clean: Transforms raw_dc_threads into clean_dc_threads (market_id FK)
    and raw_dc_messages into clean_dc_messages (vote stance).
    Supports market_id: \\d+ pattern matching + fallback slug lookup against raw_pm_markets.

    Incremental optimization:
    - clean_dc_threads: only transforms threads missing from clean_dc_threads,
      unlinked threads (market_id IS NULL), or touched recently.
    - clean_dc_messages: only extracts votes from new messages not yet in clean_dc_messages
      and loads with on_conflict="ignore" (immutable event append).
    """
    logger.info("Phase 1 Clean: Transforming raw_dc_threads into clean_dc_threads...")
    conn = get_db_conn()

    try:
        # Pre-build slug-to-market_id map from raw_pm_markets for fallback resolution
        slug_to_mid = {}
        try:
            slug_rows = conn.execute(
                "SELECT slug, id FROM raw_pm_markets WHERE slug IS NOT NULL AND slug != ''"
            ).fetchall()
            slug_to_mid = {r[0]: r[1] for r in slug_rows}
        except Exception as e:
            logger.debug(f"Slug-to-market_id map build notice: {e}")

        # Check if clean tables exist to enable incremental scans
        threads_table_exists = False
        msgs_table_exists = False
        try:
            existing_tables = [
                r[0]
                for r in conn.execute(
                    "SELECT table_name FROM information_schema.tables WHERE table_name IN ('clean_dc_threads', 'clean_dc_messages')"
                ).fetchall()
            ]
            threads_table_exists = "clean_dc_threads" in existing_tables
            msgs_table_exists = "clean_dc_messages" in existing_tables
        except Exception as e:
            logger.debug(f"Information schema table check notice: {e}")

        if not full_refresh and threads_table_exists:
            run_filter = f"OR r._source_run_id = '{run_id}'" if run_id else ""
            query_threads = f"""
                SELECT r.id as thread_id, r.author_username, r.timestamp, r.content, r.embeds 
                FROM raw_dc_threads r
                LEFT JOIN clean_dc_threads c ON r.id = c.thread_id
                WHERE c.thread_id IS NULL 
                   OR c.market_id IS NULL
                   {run_filter}
                   OR r._updated_at >= now() - INTERVAL '30 minutes'
            """
            logger.info(f"Phase 1 Clean: Performing incremental transform on raw_dc_threads (run_id={run_id})...")
        else:
            query_threads = "SELECT id as thread_id, author_username, timestamp, content, embeds FROM raw_dc_threads"
            logger.info("Phase 1 Clean: Performing full transform on raw_dc_threads...")

        df_threads = conn.execute(query_threads).pl()

        if not df_threads.is_empty():
            candidate_tids = [f"'{t}'" for t in df_threads["thread_id"].to_list()]
            tids_in_clause = ", ".join(candidate_tids)
            query_messages = f"""
                SELECT thread_id, content, embeds 
                FROM raw_dc_messages 
                WHERE thread_id IN ({tids_in_clause})
                  AND (content LIKE '%market_id:%' OR content LIKE '%polymarket.com%' OR content LIKE '%assertion%' OR content LIKE '%0x%')
            """
            df_msgs = conn.execute(query_messages).pl()

            mid_mapping = {}
            assertion_mapping = {}
            market_id_pattern = re.compile(r"market_id:\s*(\d+)")
            slug_pattern = re.compile(r"polymarket\.com/(?:event|market)/([a-zA-Z0-9_-]+)")
            assertion_pattern = re.compile(
                r"(?i)(?:assertion_?id|assertionId)[=: ]+\s*(0x[a-fA-F0-9]{64}|[a-fA-F0-9]{10,66})|"
                r"oracle\.uma\.xyz/(?:request|assertion)[^\s\"'>]*(?:assertionId|id)=(0x[a-fA-F0-9]{64}|[0-9a-fA-F]{10,66})|"
                r"\b(0x[a-fA-F0-9]{64})\b"
            )

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

            def resolve_assertion_id(text: str, embeds: str = "") -> Optional[str]:
                combined = f"{text or ''} {embeds or ''}"
                match = assertion_pattern.search(combined)
                if match:
                    for g in match.groups():
                        if g:
                            return g
                return None

            if not df_msgs.is_empty():
                for row in df_msgs.to_dicts():
                    t_id = row["thread_id"]
                    if t_id not in mid_mapping:
                        res_mid = resolve_mid_from_text(row.get("content", ""))
                        if res_mid:
                            mid_mapping[t_id] = res_mid
                    if t_id not in assertion_mapping:
                        res_aid = resolve_assertion_id(row.get("content", ""), row.get("embeds", ""))
                        if res_aid:
                            assertion_mapping[t_id] = res_aid

            for row in df_threads.to_dicts():
                t_id = row["thread_id"]
                if t_id not in mid_mapping:
                    res_mid = resolve_mid_from_text(row.get("content", ""))
                    if res_mid:
                        mid_mapping[t_id] = res_mid
                if t_id not in assertion_mapping:
                    res_aid = resolve_assertion_id(row.get("content", ""), row.get("embeds", ""))
                    if res_aid:
                        assertion_mapping[t_id] = res_aid

            mid_df = pl.DataFrame(
                {
                    "thread_id": list(mid_mapping.keys()),
                    "market_id": list(mid_mapping.values()),
                },
                schema={"thread_id": pl.String, "market_id": pl.String},
            )

            aid_df = pl.DataFrame(
                {
                    "thread_id": list(assertion_mapping.keys()),
                    "assertion_id": list(assertion_mapping.values()),
                },
                schema={"thread_id": pl.String, "assertion_id": pl.String},
            )

            if not mid_df.is_empty():
                df_threads = df_threads.join(mid_df, on="thread_id", how="left")
            else:
                df_threads = df_threads.with_columns(
                    pl.lit(None, dtype=pl.String).alias("market_id")
                )

            if not aid_df.is_empty():
                df_threads = df_threads.join(aid_df, on="thread_id", how="left")
            else:
                df_threads = df_threads.with_columns(
                    pl.lit(None, dtype=pl.String).alias("assertion_id")
                )

            # Drop embeds before writing to clean_dc_threads
            if "embeds" in df_threads.columns:
                df_threads = df_threads.drop("embeds")

            linked_count = df_threads.filter(pl.col("market_id").is_not_null()).height
            aid_count = df_threads.filter(pl.col("assertion_id").is_not_null()).height
            total_count = len(df_threads)
            logger.info(f"clean_dc_threads: {linked_count}/{total_count} linked to market_id, {aid_count}/{total_count} extracted assertion_id.")

            records_t = df_threads.to_dicts()
            load_json_to_table("clean_dc_threads", records_t, pk="thread_id", run_id=run_id, on_conflict="update")
            logger.info(f"Loaded {len(records_t)} records into clean_dc_threads")
        else:
            logger.info("Phase 1 Clean: No new or unlinked threads to process.")

        logger.info("Phase 1 Clean: Transforming raw_dc_messages into clean_dc_messages...")
        if not full_refresh and msgs_table_exists:
            query_m = """
                SELECT r.id as message_id, r.thread_id, r.author_username, r.timestamp, r.content, r.embeds 
                FROM raw_dc_messages r
                LEFT JOIN clean_dc_messages c ON r.id = c.message_id
                WHERE c.message_id IS NULL
            """
            logger.info(f"Phase 1 Clean: Performing incremental vote extraction on new messages...")
        else:
            query_m = "SELECT id as message_id, thread_id, author_username, timestamp, content, embeds FROM raw_dc_messages"
            logger.info("Phase 1 Clean: Performing full catalog vote extraction on raw_dc_messages...")

        df_m = conn.execute(query_m).pl()

        if not df_m.is_empty():
            # Extract vote stance
            df_m = df_m.with_columns(
                pl.col("content")
                .str.extract(r"(?i)\b(P[1-4])\b", 1)
                .str.to_uppercase()
                .alias("vote_type")
            )
            # Filter for vote messages
            df_votes = df_m.filter(pl.col("vote_type").is_not_null())

            if not df_votes.is_empty():
                url_pattern = re.compile(r"https?://[^\s<>\"']+")

                def extract_urls(content: Optional[str], embeds: Optional[str]) -> list[str]:
                    found = []
                    if content:
                        found.extend(url_pattern.findall(content))
                    if embeds:
                        found.extend(url_pattern.findall(embeds))
                    return list(set(found))

                urls_list = [
                    extract_urls(c, e)
                    for c, e in zip(df_votes["content"], df_votes["embeds"])
                ]

                df_votes = df_votes.with_columns(
                    pl.Series("urls", urls_list, dtype=pl.List(pl.String))
                ).drop("embeds")

                records_m = df_votes.to_dicts()
                # Discord messages are immutable event logs: append-only with on_conflict="ignore"
                load_json_to_table("clean_dc_messages", records_m, pk="message_id", run_id=run_id, on_conflict="ignore")
                logger.info(f"Loaded {len(records_m)} records into clean_dc_messages (append-only)")
            else:
                logger.info("Phase 1 Clean: No vote stance messages detected in new records.")
        else:
            logger.info("Phase 1 Clean: No new messages to extract votes from.")

        logger.success("Phase 1 Clean Complete.")
    finally:
        conn.close()
