import json
import sqlite3
import sys

import polars as pl
from loguru import logger

from config import PipelineConfig
from db_utils import get_sqlite_conn, load_json_to_table


def transform_pm_markets() -> None:
    logger.info("Transforming clean_pm_markets...")
    query = """
        SELECT 
            condition_id, id as market_id, uma_question_id, slug, question, 
            active, closed, uma_resolution_status, uma_bond, uma_reward, 
            neg_risk, custom_liveness, outcome_prices
        FROM raw_pm_markets
        WHERE condition_id IS NOT NULL
    """
    conn = get_sqlite_conn()
    df = pl.read_database(query, conn)
    conn.close()

    if df.is_empty():
        logger.warning("No pm markets to transform.")
        return

    import json
    records = df.to_dicts()
    
    for r in records:
        prices_str = r.pop("outcome_prices", None)
        r["yes_price"] = None
        r["no_price"] = None
        if prices_str:
            try:
                arr = json.loads(prices_str)
                if len(arr) >= 2:
                    r["yes_price"] = float(arr[0])
                    r["no_price"] = float(arr[1])
            except Exception:
                pass

    load_json_to_table("clean_pm_markets", records, pk="condition_id")


def transform_dc_threads() -> None:
    logger.info("Transforming clean_dc_threads...")
    # 1. Fetch raw threads
    query_threads = "SELECT id as thread_id, author_username, timestamp, content FROM raw_dc_threads"

    # 2. Fetch raw messages to extract market_id
    query_messages = """
        SELECT thread_id, content 
        FROM raw_dc_messages 
        WHERE content LIKE '%market_id:%'
    """

    conn = get_sqlite_conn()
    df_threads = pl.read_database(query_threads, conn)
    df_msgs = pl.read_database(query_messages, conn)
    conn.close()

    if df_threads.is_empty():
        logger.warning("No discord threads to transform.")
        return

    # Extract market_id from messages
    mid_mapping = {}
    
    import re
    market_id_pattern = re.compile(r"market_id:\s*(\d+)")

    for row in df_msgs.to_dicts():
        t_id = row["thread_id"]
        if t_id in mid_mapping:
            continue
            
        content = row.get("content", "")
        match = market_id_pattern.search(content)
        if match:
            mid_mapping[t_id] = match.group(1)

    # Join market_id mapping
    mid_df = pl.DataFrame({
        "thread_id": list(mid_mapping.keys()),
        "market_id": list(mid_mapping.values())
    }, schema={"thread_id": pl.Utf8, "market_id": pl.Utf8})

    if not mid_df.is_empty():
        df_threads = df_threads.join(mid_df, on="thread_id", how="left")
    else:
        df_threads = df_threads.with_columns(pl.lit(None, dtype=pl.Utf8).alias("market_id"))

    records = df_threads.to_dicts()
    load_json_to_table("clean_dc_threads", records, pk="thread_id")


def transform_dc_messages() -> None:
    logger.info("Transforming clean_dc_messages (Votes)...")
    query = "SELECT id as message_id, thread_id, author_username, timestamp, content FROM raw_dc_messages"

    conn = get_sqlite_conn()
    df = pl.read_database(query, conn)
    conn.close()

    if df.is_empty():
        logger.warning("No discord messages to transform.")
        return

    # Extract votes using regex: \b represents a word boundary.
    # Rust regex engine in Polars does not support lookarounds.
    df = df.with_columns(
        pl.col("content").str.extract(r"(?i)\b(P[1-4])\b", 1).str.to_uppercase().alias("vote_type")
    )

    # Filter to only rows that have a vote
    df_votes = df.filter(pl.col("vote_type").is_not_null())

    # Drop content to save space in clean layer
    df_votes = df_votes.drop("content")

    if not df_votes.is_empty():
        records = df_votes.to_dicts()
        load_json_to_table("clean_dc_messages", records, pk="message_id")
    else:
        logger.info("No votes found to transform.")


def transform_polygon_ancillary() -> None:
    logger.info("Transforming clean_polygon_ancillary...")
    query = "SELECT question_id as uma_question_id, oracle_version, ancillary_data_decoded FROM raw_polygon_ancillary"

    conn = get_sqlite_conn()
    df = pl.read_database(query, conn)
    conn.close()

    if df.is_empty():
        logger.warning("No polygon ancillary records to transform.")
        return

    records = df.to_dicts()
    load_json_to_table("clean_polygon_ancillary", records, pk="uma_question_id")


def create_disputes_view() -> None:
    logger.info("Creating disputes_view...")
    conn = get_sqlite_conn()
    cursor = conn.cursor()

    cursor.execute("DROP VIEW IF EXISTS disputes_view;")
    
    view_sql = """
    CREATE VIEW disputes_view AS
    SELECT 
        t.thread_id,
        m.condition_id,
        m.question,
        m.slug,
        m.uma_resolution_status,
        m.uma_bond,
        m.uma_reward,
        m.neg_risk,
        m.yes_price,
        m.no_price,
        COUNT(CASE WHEN v.vote_type = 'P1' THEN 1 END) AS p1_votes,
        COUNT(CASE WHEN v.vote_type = 'P2' THEN 1 END) AS p2_votes,
        COUNT(CASE WHEN v.vote_type = 'P3' THEN 1 END) AS p3_votes,
        COUNT(CASE WHEN v.vote_type = 'P4' THEN 1 END) AS p4_votes,
        p.ancillary_data_decoded
    FROM clean_dc_threads t
    JOIN clean_pm_markets m ON t.market_id = m.market_id
    LEFT JOIN clean_dc_messages v ON t.thread_id = v.thread_id
    LEFT JOIN clean_polygon_ancillary p ON m.uma_question_id = p.uma_question_id
    GROUP BY t.thread_id;
    """

    cursor.execute("DROP VIEW IF EXISTS disputes_view")
    cursor.execute(view_sql)
    conn.commit()
    conn.close()


def main() -> int:
    try:
        transform_pm_markets()
        transform_dc_threads()
        transform_dc_messages()
        transform_polygon_ancillary()
        create_disputes_view()
        logger.success("Transformation layer complete.")
        return 0
    except Exception as e:
        logger.exception(f"Transformation failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
