import sys
from loguru import logger
from db_utils import get_db_conn


def create_views(conn=None) -> None:
    """
    Creates/updates analytics views and macro functions in MotherDuck:
    1. fn_dc_user_profiles_as_of(as_of_ts): Table-valued macro for leak-free backtests.
    2. vw_dc_user_profiles: Live view evaluated at now().
    """
    should_close = False
    if conn is None:
        conn = get_db_conn()
        should_close = True

    logger.info("Initializing MotherDuck user profile calibration views & macros...")

    # 1. Table-Valued Macro Function for parameterized / leak-free backtesting
    macro_sql = """
    CREATE OR REPLACE MACRO fn_dc_user_profiles_as_of(as_of_ts) AS TABLE
    SELECT 
        v.author_username,
        COUNT(*) AS total_predictions,
        COUNT(CASE 
            WHEN v.vote_type IN ('P1', 'P2') 
             AND (m.closed = true OR COALESCE(m.uma_resolution_status, '') = 'resolved') 
             AND (m.yes_price > 0.99 OR m.no_price > 0.99) 
            THEN 1 
        END) AS gradeable_predictions,
        SUM(CASE 
            WHEN (m.closed = true OR COALESCE(m.uma_resolution_status, '') = 'resolved') AND m.yes_price > 0.99 AND v.vote_type = 'P2' THEN 1
            WHEN (m.closed = true OR COALESCE(m.uma_resolution_status, '') = 'resolved') AND m.no_price > 0.99 AND v.vote_type = 'P1' THEN 1
            ELSE 0 
        END) AS correct_predictions,
        CAST(SUM(CASE 
            WHEN (m.closed = true OR COALESCE(m.uma_resolution_status, '') = 'resolved') AND m.yes_price > 0.99 AND v.vote_type = 'P2' THEN 1
            WHEN (m.closed = true OR COALESCE(m.uma_resolution_status, '') = 'resolved') AND m.no_price > 0.99 AND v.vote_type = 'P1' THEN 1
            ELSE 0 
        END) AS DOUBLE) / NULLIF(COUNT(CASE 
            WHEN v.vote_type IN ('P1', 'P2') 
             AND (m.closed = true OR COALESCE(m.uma_resolution_status, '') = 'resolved') 
             AND (m.yes_price > 0.99 OR m.no_price > 0.99) 
            THEN 1 
        END), 0) AS lifetime_accuracy,
        (COUNT(CASE 
            WHEN v.vote_type IN ('P1', 'P2') 
             AND (m.closed = true OR COALESCE(m.uma_resolution_status, '') = 'resolved') 
             AND (m.yes_price > 0.99 OR m.no_price > 0.99) 
            THEN 1 
        END) >= 5) AS is_calibrated,
        MAX(v.timestamp) AS last_voted_at
    FROM clean_dc_messages v
    JOIN clean_dc_threads t ON v.thread_id = t.thread_id
    JOIN clean_pm_markets m ON t.market_id = m.market_id
    WHERE v.author_username != 'UMA Herald'
      AND v.timestamp <= TRY_CAST(as_of_ts AS TIMESTAMPTZ)
      AND (m.closed_time IS NULL OR m.closed_time <= TRY_CAST(as_of_ts AS TIMESTAMPTZ))
    GROUP BY v.author_username;
    """

    # 2. Live View evaluated at current time now()
    view_sql = """
    CREATE OR REPLACE VIEW vw_dc_user_profiles AS
    SELECT * FROM fn_dc_user_profiles_as_of(now());
    """

    try:
        conn.execute(macro_sql)
        logger.info("Successfully created/updated macro function 'fn_dc_user_profiles_as_of(as_of_ts)'")
        conn.execute(view_sql)
        logger.info("Successfully created/updated view 'vw_dc_user_profiles'")
    finally:
        if should_close:
            conn.close()


import argparse


def test_user_profile_views(as_of: str = "2026-08-01") -> None:
    """
    Executes test queries against vw_dc_user_profiles and fn_dc_user_profiles_as_of().
    """
    clean_as_of = as_of.strip()
    if "T" not in clean_as_of and " " not in clean_as_of:
        clean_as_of = f"{clean_as_of} 00:00:00Z"

    conn = get_db_conn()
    try:
        create_views(conn)

        logger.info("--- Testing Live View: SELECT * FROM vw_dc_user_profiles ---")
        df_live = conn.execute(
            """
            SELECT author_username, total_predictions, gradeable_predictions, correct_predictions, ROUND(lifetime_accuracy, 4) as accuracy, is_calibrated
            FROM vw_dc_user_profiles
            ORDER BY gradeable_predictions DESC, lifetime_accuracy DESC
            LIMIT 10
            """
        ).df()
        print("\nTop 10 Discord Users (Live View):")
        print(df_live.to_string(index=False))

        logger.info(f"--- Testing Backtest Macro: SELECT * FROM fn_dc_user_profiles_as_of('{clean_as_of}') ---")
        df_backtest = conn.execute(
            f"""
            SELECT author_username, total_predictions, gradeable_predictions, correct_predictions, ROUND(lifetime_accuracy, 4) as accuracy, is_calibrated
            FROM fn_dc_user_profiles_as_of('{clean_as_of}')
            ORDER BY gradeable_predictions DESC
            LIMIT 10
            """
        ).df()
        print(f"\nTop 10 Discord Users (As-Of {clean_as_of} Backtest):")
        print(df_backtest.to_string(index=False))

    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MotherDuck User Profile Views & Backtest Macro Runner")
    parser.add_argument(
        "--as-of",
        type=str,
        default="2026-08-01",
        help="As-of cutoff timestamp for backtest macro query (YYYY-MM-DD or ISO8601)",
    )
    args = parser.parse_args()
    test_user_profile_views(as_of=args.as_of)
