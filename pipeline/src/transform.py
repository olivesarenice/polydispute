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
    mid_df = pl.DataFrame(
        {
            "thread_id": list(mid_mapping.keys()),
            "market_id": list(mid_mapping.values()),
        },
        schema={"thread_id": pl.Utf8, "market_id": pl.Utf8},
    )

    if not mid_df.is_empty():
        df_threads = df_threads.join(mid_df, on="thread_id", how="left")
    else:
        df_threads = df_threads.with_columns(
            pl.lit(None, dtype=pl.Utf8).alias("market_id")
        )

    total = len(df_threads)
    linked = df_threads.filter(pl.col("market_id").is_not_null()).height
    logger.info(
        f"clean_dc_threads market_id coverage: {linked}/{total} linked "
        f"({total - linked} unlinked — herald bot message not found or older format)"
    )

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
        pl.col("content")
        .str.extract(r"(?i)\b(P[1-4])\b", 1)
        .str.to_uppercase()
        .alias("vote_type")
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


def create_user_profiles_view() -> None:
    """
    Phase 2: Computes lifetime accuracy for each Discord user against resolved markets.

    Key mapping (from UMA DVM semantics):
      P2 = YES  (yes_price settles to 1.0)
      P1 = NO   (no_price settles to 1.0)

    Denominator counts ONLY graded directional votes (P1/P2 on resolved markets).
    P3 (Unknown) and P4 (too-early) are excluded — they can never match a YES/NO
    settlement and would silently drag accuracy down.

    Uses >0.99 threshold instead of exact =1.0 to tolerate floating-point settlement
    artefacts (e.g. 0.9999).

    SYSTEM_USERNAMES (e.g. UMA Herald) are excluded — their messages contain all
    vote labels as template text, not genuine predictions.
    """
    logger.info("Creating discord_user_profiles view...")
    conn = get_sqlite_conn()

    # Build SQL-safe exclusion list from config
    excluded = ", ".join(f"'{u}'" for u in sorted(PipelineConfig.SYSTEM_USERNAMES))

    view_sql = f"""
    CREATE VIEW discord_user_profiles AS
    SELECT
        v.author_username,
        -- total_predictions: only graded directional votes (P1/P2)
        -- used as the calibration gate (MIN_CALIBRATION_VOTES)
        COUNT(CASE WHEN v.vote_type IN ('P1', 'P2') THEN 1 END) AS total_predictions,
        SUM(
            CASE
                -- P2 = YES: correct when yes_price settles near 1.0
                WHEN m.yes_price > 0.99 AND v.vote_type = 'P2' THEN 1
                -- P1 = NO:  correct when no_price settles near 1.0
                WHEN m.no_price  > 0.99 AND v.vote_type = 'P1' THEN 1
                ELSE 0
            END
        ) AS correct_predictions,
        -- NULLIF guards divide-by-zero for users who only ever posted P3/P4
        CAST(SUM(
            CASE
                WHEN m.yes_price > 0.99 AND v.vote_type = 'P2' THEN 1
                WHEN m.no_price  > 0.99 AND v.vote_type = 'P1' THEN 1
                ELSE 0
            END
        ) AS REAL)
        / NULLIF(COUNT(CASE WHEN v.vote_type IN ('P1', 'P2') THEN 1 END), 0)
            AS lifetime_accuracy
    FROM clean_dc_messages v
    JOIN clean_dc_threads t ON v.thread_id = t.thread_id
    JOIN clean_pm_markets m ON t.market_id = m.market_id
    WHERE m.uma_resolution_status = 'resolved'
      AND v.author_username NOT IN ({excluded})
    GROUP BY v.author_username;
    """

    conn.execute("DROP VIEW IF EXISTS discord_user_profiles")
    conn.execute(view_sql)
    conn.commit()
    conn.close()
    logger.info("discord_user_profiles view created.")


def create_disputes_view() -> None:
    """
    Phase 3: Aggregates raw vote counts AND calibration-weighted vote scores
    per dispute thread. Weighted scores feed directly into the tau formula.

    weighted_p1_votes / weighted_p2_votes: sum of lifetime_accuracy for each
    calibrated voter (>= MIN_CALIBRATION_VOTES graded predictions). Uncalibrated
    users contribute 0 weight.
    """
    logger.info("Creating disputes_view...")
    conn = get_sqlite_conn()
    cursor = conn.cursor()

    # Build SQL-safe exclusion list from config
    excluded = ", ".join(f"'{u}'" for u in sorted(PipelineConfig.SYSTEM_USERNAMES))

    view_sql = f"""
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

        -- Raw unweighted vote counts (system accounts excluded)
        COUNT(CASE WHEN v.vote_type = 'P1' THEN 1 END) AS p1_votes,
        COUNT(CASE WHEN v.vote_type = 'P2' THEN 1 END) AS p2_votes,
        COUNT(CASE WHEN v.vote_type = 'P3' THEN 1 END) AS p3_votes,
        COUNT(CASE WHEN v.vote_type = 'P4' THEN 1 END) AS p4_votes,

        -- Tier 2 weighted scores: sum of accuracy for calibrated voters only.
        -- Users below MIN_CALIBRATION_VOTES threshold contribute 0.
        SUM(
            CASE
                WHEN v.vote_type = 'P1'
                 AND COALESCE(u.total_predictions, 0) >= {PipelineConfig.MIN_CALIBRATION_VOTES}
                THEN u.lifetime_accuracy
                ELSE 0
            END
        ) AS weighted_p1_votes,
        SUM(
            CASE
                WHEN v.vote_type = 'P2'
                 AND COALESCE(u.total_predictions, 0) >= {PipelineConfig.MIN_CALIBRATION_VOTES}
                THEN u.lifetime_accuracy
                ELSE 0
            END
        ) AS weighted_p2_votes,

        p.ancillary_data_decoded
    FROM clean_dc_threads t
    JOIN clean_pm_markets m ON t.market_id = m.market_id
    -- Exclude system accounts at join time: cleans both raw counts and weighted scores
    LEFT JOIN clean_dc_messages v
        ON t.thread_id = v.thread_id
        AND v.author_username NOT IN ({excluded})
    LEFT JOIN discord_user_profiles u ON v.author_username = u.author_username
    LEFT JOIN clean_polygon_ancillary p ON m.uma_question_id = p.uma_question_id
    GROUP BY t.thread_id;
    """

    cursor.execute("DROP VIEW IF EXISTS disputes_view")
    cursor.execute(view_sql)
    conn.commit()
    conn.close()
    logger.info("disputes_view created.")


def main() -> int:
    try:
        transform_pm_markets()
        transform_dc_threads()
        transform_dc_messages()
        transform_polygon_ancillary()
        create_user_profiles_view()  # Phase 2: must precede disputes_view
        create_disputes_view()  # Phase 3: joins user profiles
        logger.success("Transformation layer complete.")
        return 0
    except Exception as e:
        logger.exception(f"Transformation failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
