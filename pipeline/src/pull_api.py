import json
import os
from datetime import datetime, timezone
from typing import Optional

from loguru import logger

from config import DiscordConfig, PipelineConfig, PolygonConfig
from connectors.discord import DiscordClient
from connectors.polygon import PolygonClient
from connectors.polymarket import PolymarketClient
from db_utils import load_json_to_table


def get_watermark(client_name: str) -> Optional[str]:
    path = os.path.join(PipelineConfig.WATERMARK_DIR, f"{client_name}.watermark")
    if os.path.exists(path):
        with open(path, "r") as f:
            return f.read().strip()
    return None


def set_watermark(client_name: str, timestamp_str: str) -> None:
    os.makedirs(PipelineConfig.WATERMARK_DIR, exist_ok=True)
    path = os.path.join(PipelineConfig.WATERMARK_DIR, f"{client_name}.watermark")
    with open(path, "w") as f:
        f.write(timestamp_str)


def get_output_path(client_name: str, current_time: datetime) -> str:
    date_str = current_time.strftime("%Y-%m-%d")
    time_str = current_time.strftime("%H-%M-%S")
    dir_path = os.path.join(PipelineConfig.RAW_DATA_DIR, client_name, date_str)
    os.makedirs(dir_path, exist_ok=True)
    return os.path.join(dir_path, f"{time_str}.json")


def run_incremental(client: str) -> None:
    """
    Designed to be run every 5 minutes by cron.
    Uses .watermark to ensure no data gaps and no overlap.
    """
    now = datetime.now(timezone.utc)
    t1 = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    t0 = get_watermark(client)

    if not t0:
        logger.warning(f"No watermark found for {client}. Defaulting to 1 day ago.")
        import datetime as dt
        t0 = (now - dt.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")

    logger.info(f"Running incremental pull for {client}: {t0} -> {t1}")

    match client:
        case "polymarket":
            pull_polymarket_and_polygon(t0, t1, now)
        case "discord":
            pull_discord(t0, t1, now)
        case _:
            logger.error(f"Unknown client: {client}")
            return

    # Only update the watermark if the run succeeded
    set_watermark(client, t1)

import sqlite3

def run_sync(client: str) -> None:
    """
    State Sync Mode: Updates live data for active markets/threads.
    Reads the clean database to know what is currently active.
    """
    now = datetime.now(timezone.utc)
    logger.info(f"Running active state sync for {client}")
    
    db_path = os.path.join(PipelineConfig.CLEAN_DATA_DIR, "polydispute.db")
    db_exists = os.path.exists(db_path)

    match client:
        case "polymarket":
            active_ids = []
            if db_exists:
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                try:
                    cursor.execute("SELECT market_id FROM clean_pm_markets WHERE closed = 0")
                    active_ids = [row[0] for row in cursor.fetchall() if row[0]]
                except sqlite3.OperationalError:
                    logger.warning("clean_pm_markets table not found in clean DB.")
                finally:
                    conn.close()
            
            if not active_ids:
                logger.info("No active Polymarket IDs found to sync.")
                return
                
            pm_client = PolymarketClient()
            chunk_size = 50
            all_markets = []
            for i in range(0, len(active_ids), chunk_size):
                chunk = active_ids[i:i+chunk_size]
                markets = pm_client.get_markets(chunk)
                all_markets.extend([m.model_dump() for m in markets])
                
            if all_markets:
                load_json_to_table("raw_pm_markets", all_markets)
                logger.info(f"Loaded {len(all_markets)} synced markets directly into raw_pm_markets")
                
        case "discord":
            dc_client = DiscordClient()
            guild_id = DiscordConfig.DISPUTES_GUILD_ID
            channel_id = DiscordConfig.DISPUTES_CHANNEL_ID
            
            thread_ids = dc_client.get_active_thread_ids(guild_id, channel_id)
            
            if not thread_ids:
                logger.info("No active Discord threads found to sync.")
                return
                
            all_data = []
            for t_id in thread_ids:
                # We mock a basic thread shell and attach its synced messages
                thread_dict = {"id": t_id, "channel_id": channel_id, "type": 18, "content": "SYNCED_THREAD"}
                messages = dc_client.get_messages(t_id, limit=100)
                thread_dict["messages"] = [m.model_dump() for m in messages]
                all_data.append(thread_dict)
                
            if all_data:
                out_path = get_output_path("discord_sync", now)
                with open(out_path, "w") as f:
                    json.dump(all_data, f, indent=2)
                logger.info(f"Saved {len(all_data)} synced Discord threads to {out_path}")
                
        case _:
            logger.error(f"Unknown client for sync: {client}")


def pull_polymarket_and_polygon(t0: str, t1: str, current_time: datetime) -> None:
    """
    Bundles PM and Polygon. Pulls new markets, fetches on-chain ancillaryData, and saves.
    """
    pm_client = PolymarketClient()
    poly_client = PolygonClient()

    events = pm_client.get_events(start_date_min=t0, start_date_max=t1)

    enriched_markets = []
    for event in events:
        for market in event.markets:
            market_dict = market.model_dump()

            # Cross-reference with Polygon
            if market.conditionId:
                try:
                    # In V3, we extract the ancillaryData from Polygon via the CTF adapter
                    uma_data = poly_client.get_uma_question(
                        adapter_address=PolygonConfig.DEFAULT_CTF_ADAPTER,
                        question_id=market.conditionId,
                    )
                    market_dict["uma_data"] = uma_data.model_dump()
                except Exception as e:
                    logger.warning(
                        f"Could not fetch polygon data for {market.conditionId}: {e}"
                    )

            enriched_markets.append(market_dict)

    if enriched_markets:
        out_path = get_output_path("polymarket", current_time)
        with open(out_path, "w") as f:
            json.dump(enriched_markets, f, indent=2)
        logger.info(f"Saved {len(enriched_markets)} enriched markets to {out_path}")
    else:
        logger.info("No new markets found. Skipping write.")


def pull_discord(t0: str, t1: str, current_time: datetime) -> None:
    """
    Fetches active threads and messages from the configured channel.
    """
    dc_client = DiscordClient()
    channel_id = DiscordConfig.DISPUTES_CHANNEL_ID

    threads = dc_client.get_thread_starters(
        channel_id=channel_id, limit=DiscordConfig.DEFAULT_LIMIT
    )

    all_data = []
    for t in threads:
        thread_dict = t.model_dump()
        messages = dc_client.get_messages(t.id, limit=100)
        thread_dict["messages"] = [m.model_dump() for m in messages]
        all_data.append(thread_dict)

    if all_data:
        out_path = get_output_path("discord", current_time)
        with open(out_path, "w") as f:
            json.dump(all_data, f, indent=2)
        logger.info(f"Saved {len(all_data)} Discord threads to {out_path}")
    else:
        logger.info("No new Discord threads found. Skipping write.")


def run_historical(client: str, t0: str, t1: str) -> None:
    """
    Manual override to pull specific historical chunks.
    Note: t0/t1 format should be YYYY-MM-DD or full ISO8601 string.
    """
    logger.info(f"Running historical pull for {client}: {t0} -> {t1}")
    now = datetime.now(timezone.utc)
    match client:
        case "polymarket":
            pull_polymarket_and_polygon(t0, t1, now)
        case "discord":
            pull_discord(t0, t1, now)
        case _:
            logger.error(f"Unknown historical client: {client}")
