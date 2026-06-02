import argparse
import sys
import uuid
from datetime import datetime, timedelta, timezone

from loguru import logger

from config import DiscordConfig
from connectors.polymarket import PolymarketClient
from connectors.discord import DiscordClient
from db_utils import get_sqlite_conn, load_json_to_table


def get_last_watermark() -> str:
    """
    Retrieve t0 dynamically from pipeline_runs.
    Uses start_time to prevent data loss of records created during the runtime.
    If no successful runs exist, default to 24 hours ago.
    """
    conn = get_sqlite_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT MAX(start_time) FROM pipeline_runs WHERE status='SUCCESS'")
    row = cursor.fetchone()
    conn.close()
    
    if row and row[0]:
        t0 = row[0]
        # Ensure it ends with Z for Polymarket API
        if not t0.endswith("Z"):
            t0 = t0.replace("+00:00", "") + "Z"
        return t0
        
    logger.warning("No previous successful pipeline runs found. Defaulting to T-24h.")
    return (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat().replace("+00:00", "Z")


def run_discovery() -> None:
    """
    Discovery: Pulls new markets and threads created since the last watermark.
    """
    t0 = get_last_watermark()
    t1 = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    logger.info(f"Running Discovery: {t0} -> {t1}")
    
    # 1. Polymarket Discovery
    pm_client = PolymarketClient()
    events = pm_client.get_events(t0, t1)
    
    raw_events = []
    raw_markets = []
    for ev in events:
        ev_dict = ev.model_dump(by_alias=False)
        markets_in_event = ev_dict.pop("markets", [])
        raw_events.append(ev_dict)
        raw_markets.extend(markets_in_event)
        
    if raw_events:
        logger.info(f"Discovered {len(raw_events)} new PM events.")
        load_json_to_table("raw_pm_events", raw_events)
        load_json_to_table("raw_pm_markets", raw_markets)

    # 2. Discord Discovery
    dc_client = DiscordClient()
    threads = dc_client.get_thread_starters(DiscordConfig.DISPUTES_CHANNEL_ID)
    
    # Filter threads created after t0 (rudimentary filter since Discord API pagination is tricky)
    t0_dt = datetime.fromisoformat(t0.replace("Z", "+00:00"))
    new_threads = []
    for t in threads:
        try:
            t_dt = datetime.fromisoformat(t.timestamp.replace("Z", "+00:00"))
            if t_dt >= t0_dt:
                new_threads.append(t)
        except Exception:
            pass
            
    if new_threads:
        logger.info(f"Discovered {len(new_threads)} new Discord threads.")
        raw_threads = [t.model_dump(by_alias=False) for t in new_threads]
        load_json_to_table("raw_dc_threads", raw_threads)


def run_sync() -> None:
    """
    Sync: Polls live prices and messages for active elements.
    """
    logger.info("Running State Sync...")
    
    conn = get_sqlite_conn()
    cursor = conn.cursor()
    
    # Sync PM
    try:
        cursor.execute("SELECT id FROM raw_pm_markets WHERE closed = 0")
        active_ids = [row[0] for row in cursor.fetchall()]
        
        if active_ids:
            pm_client = PolymarketClient()
            synced_markets = pm_client.get_markets(active_ids)
            raw_markets = [m.model_dump(by_alias=False) for m in synced_markets]
            logger.info(f"Synced {len(raw_markets)} active PM markets.")
            load_json_to_table("raw_pm_markets", raw_markets)
    except sqlite3.OperationalError as e:
        logger.warning(f"Skipping PM Sync: {e}")
        
    # Sync Discord
    # We query Discord's active threads, then fetch messages for them
    dc_client = DiscordClient()
    active_thread_ids = dc_client.get_active_thread_ids(
        DiscordConfig.DISPUTES_GUILD_ID, 
        DiscordConfig.DISPUTES_CHANNEL_ID
    )
    
    all_synced_messages = []
    for t_id in active_thread_ids:
        msgs = dc_client.get_messages(t_id, limit=50) # Just fetch the last 50 for quick sync
        all_synced_messages.extend([m.model_dump(by_alias=False) for m in msgs])
        
    if all_synced_messages:
        logger.info(f"Synced {len(all_synced_messages)} messages from active threads.")
        load_json_to_table("raw_dc_messages", all_synced_messages)
        
    conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="ELT Cron Runner")
    parser.parse_args()

    run_id = f"cron_{uuid.uuid4()}"
    start_time = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    conn = get_sqlite_conn()
    conn.execute(
        "INSERT INTO pipeline_runs (run_id, mode, start_time, status) VALUES (?, ?, ?, ?)",
        (run_id, "cron_incremental", start_time, "RUNNING")
    )
    conn.commit()
    conn.close()

    try:
        run_discovery()
        run_sync()
        
        end_time = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        conn = get_sqlite_conn()
        conn.execute(
            "UPDATE pipeline_runs SET end_time=?, status=? WHERE run_id=?",
            (end_time, "SUCCESS", run_id)
        )
        conn.commit()
        return 0
    except Exception as e:
        logger.exception(f"Cron runner failed: {e}")
        end_time = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        conn = get_sqlite_conn()
        conn.execute(
            "UPDATE pipeline_runs SET end_time=?, status=? WHERE run_id=?",
            (end_time, "FAILED", run_id)
        )
        conn.commit()
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
