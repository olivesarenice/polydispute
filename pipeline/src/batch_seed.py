import argparse
import json
import os
import sqlite3
import sys
import uuid
from datetime import datetime, timedelta
from typing import List, Dict, Any

from loguru import logger

from config import PipelineConfig, DiscordConfig
from connectors.polymarket import PolymarketClient
from connectors.discord import DiscordClient
from db_utils import get_sqlite_conn, load_json_to_table
from dotenv import load_dotenv

load_dotenv()


def seed_polymarket(t0_str: str, t1_str: str) -> None:
    """
    Batch pull for Polymarket. Uses time-chunking to prevent memory bloat
    on massive historical queries, dumps to tmp JSON, loads to SQLite, and wipes tmp.
    """
    logger.info(f"Seeding Polymarket from {t0_str} to {t1_str}")
    client = PolymarketClient()

    # Parse inputs (assume ISO 8601 or YYYY-MM-DD)
    if "T" not in t0_str:
        t0_str += "T00:00:00Z"
    if "T" not in t1_str:
        t1_str += "T00:00:00Z"

    start_dt = datetime.fromisoformat(t0_str.replace("Z", "+00:00"))
    end_dt = datetime.fromisoformat(t1_str.replace("Z", "+00:00"))

    current_start = start_dt
    chunk_days = 7

    while current_start < end_dt:
        current_end = min(current_start + timedelta(days=chunk_days), end_dt)

        t_start = current_start.isoformat().replace("+00:00", "Z")
        t_end = current_end.isoformat().replace("+00:00", "Z")

        logger.info(f"Fetching PM chunk: {t_start} -> {t_end}")

        # Paginate through the API for this specific 7-day chunk
        offset = 0
        limit = 500
        chunk_events = []

        while True:
            events = client.get_events(t_start, t_end, offset=offset, limit=limit)
            chunk_events.extend(events)
            if len(events) < limit:
                break
            offset += limit

        if not chunk_events:
            logger.info("No events in this chunk. Skipping.")
            current_start = current_end
            continue

        # Write to tmp
        tmp_id = str(uuid.uuid4())
        tmp_path = os.path.join(PipelineConfig.TMP_DATA_DIR, f"pm_{tmp_id}.json")
        os.makedirs(PipelineConfig.TMP_DATA_DIR, exist_ok=True)

        raw_events = []
        raw_markets = []

        for ev in chunk_events:
            ev_dict = ev.model_dump(by_alias=False)
            markets_in_event = ev_dict.pop("markets", [])
            raw_events.append(ev_dict)
            raw_markets.extend(markets_in_event)

        payload = {"events": raw_events, "markets": raw_markets}
        with open(tmp_path, "w") as f:
            json.dump(payload, f)

        # Load to DB
        logger.info(
            f"Loading {len(raw_events)} events and {len(raw_markets)} markets into DB from tmp..."
        )
        load_json_to_table("raw_pm_events", raw_events)
        load_json_to_table("raw_pm_markets", raw_markets)

        # Cleanup
        os.remove(tmp_path)
        logger.info(f"Cleaned up {tmp_path}")

        current_start = current_end


def seed_discord(t0_str: str, t1_str: str) -> None:
    """
    Batch pull for Discord. Discord pagination relies on message IDs (before=X).
    Because we only scrape #disputes, it's safer to just fetch backwards with a high limit.
    """
    logger.info(
        f"Seeding Discord (t0/t1 bounds are implicitly governed by API limits currently)"
    )
    client = DiscordClient()
    channel_id = DiscordConfig.DISPUTES_CHANNEL_ID

    # In batch mode, we pull up to 5000 old disputes
    limit = 5000
    logger.info(f"Fetching Discord thread starters from {t0_str} to {t1_str} (up to {limit})...")
    threads = client.get_thread_starters(channel_id, limit=limit, t0_str=t0_str, t1_str=t1_str)

    if not threads:
        logger.info("No Discord threads found.")
        return
        
    raw_threads = [t.model_dump(by_alias=False) for t in threads]
    
    # Dump threads to tmp
    tmp_id = str(uuid.uuid4())
    tmp_path_threads = os.path.join(PipelineConfig.TMP_DATA_DIR, f"dc_threads_{tmp_id}.json")
    os.makedirs(PipelineConfig.TMP_DATA_DIR, exist_ok=True)
    
    with open(tmp_path_threads, "w") as f:
        json.dump(raw_threads, f)
        
    logger.info(f"Loading {len(raw_threads)} Discord threads into DB from tmp...")
    load_json_to_table("raw_dc_threads", raw_threads)
    
    os.remove(tmp_path_threads)
    
    # Fetch all historical messages within those threads
    logger.info(f"Fetching historical messages for {len(threads)} threads...")
    all_raw_messages = []
    
    # We will chunk message writing to prevent massive memory usage
    for i, t in enumerate(threads):
        try:
            msgs = client.get_messages(t.id, limit=100) # Discord thread limit usually < 100
            all_raw_messages.extend([m.model_dump(by_alias=False) for m in msgs])
        except Exception as e:
            logger.warning(f"Failed to fetch msgs for thread {t.id}: {e}")
            
        # Write to DB every 500 threads
        if (i + 1) % 500 == 0 or (i + 1) == len(threads):
            if all_raw_messages:
                tmp_path_msgs = os.path.join(PipelineConfig.TMP_DATA_DIR, f"dc_msgs_{uuid.uuid4()}.json")
                with open(tmp_path_msgs, "w") as f:
                    json.dump(all_raw_messages, f)
                    
                logger.info(f"Loading {len(all_raw_messages)} Discord messages into DB...")
                load_json_to_table("raw_dc_messages", all_raw_messages)
                os.remove(tmp_path_msgs)
                all_raw_messages = [] # reset buffer


def seed_discord_from_file(filepath: str) -> None:
    """
    Bypasses API and seeds Discord tables directly from a raw JSON file dump.
    The file is expected to contain a list of raw Discord message dictionaries.
    """
    logger.info(f"Seeding Discord from local file: {filepath}")
    
    with open(filepath, "r") as f:
        data = json.load(f)
        
    raw_threads = []
    raw_messages = []
    
    for raw in data:
        if raw.get("type") == 18 or "thread" in raw:
            try:
                # Parse through DiscordThread model to flatten author and alias channel_id
                t = DiscordThread(**raw)
                raw_threads.append(t.model_dump(by_alias=False))
            except Exception as e:
                logger.warning(f"Failed to parse thread {raw.get('id')}: {e}")
        else:
            try:
                m = DiscordMessage(**raw)
                raw_messages.append(m.model_dump(by_alias=False))
            except Exception as e:
                logger.warning(f"Failed to parse message {raw.get('id')}: {e}")
                
    if raw_threads:
        logger.info(f"Loading {len(raw_threads)} threads from file into DB...")
        load_json_to_table("raw_dc_threads", raw_threads)
        
    if raw_messages:
        logger.info(f"Loading {len(raw_messages)} messages from file into DB...")
        load_json_to_table("raw_dc_messages", raw_messages)


def main() -> int:
    parser = argparse.ArgumentParser(description="ELT Batch Seeder")
    parser.add_argument(
        "--client", type=str, choices=["polymarket", "discord"], required=True
    )
    parser.add_argument("--t0", type=str, required=False, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--t1", type=str, required=False, help="End date (YYYY-MM-DD)")
    parser.add_argument("--from_file", type=str, required=False, help="Bypass API and load from local JSON file")
    args = parser.parse_args()

    # Create orchestrator record
    run_id = f"batch_{uuid.uuid4()}"
    start_time = datetime.utcnow().isoformat()

    conn = get_sqlite_conn()
    conn.execute(
        "INSERT INTO pipeline_runs (run_id, mode, start_time, status) VALUES (?, ?, ?, ?)",
        (run_id, "batch_seed", start_time, "RUNNING"),
    )
    conn.commit()
    conn.close()

    try:
        if args.client == "polymarket":
            if not args.t0 or not args.t1:
                raise ValueError("--t0 and --t1 are required for polymarket client")
            seed_polymarket(args.t0, args.t1)
        elif args.client == "discord":
            if args.from_file:
                seed_discord_from_file(args.from_file)
            else:
                if not args.t0 or not args.t1:
                    raise ValueError("--t0 and --t1 are required for discord client without --from_file")
                seed_discord(args.t0, args.t1)

        end_time = datetime.utcnow().isoformat()
        conn = get_sqlite_conn()
        conn.execute(
            "UPDATE pipeline_runs SET end_time=?, status=? WHERE run_id=?",
            (end_time, "SUCCESS", run_id),
        )
        conn.commit()
        return 0
    except Exception as e:
        logger.exception(f"Batch seed failed: {e}")
        end_time = datetime.utcnow().isoformat()
        conn = get_sqlite_conn()
        conn.execute(
            "UPDATE pipeline_runs SET end_time=?, status=? WHERE run_id=?",
            (end_time, "FAILED", run_id),
        )
        conn.commit()
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
