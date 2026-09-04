import os
import sys
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st

# Setup sys.path to import db_utils from pipeline/src
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PIPELINE_SRC = PROJECT_ROOT / "pipeline" / "src"
if str(PIPELINE_SRC) not in sys.path:
    sys.path.insert(0, str(PIPELINE_SRC))

try:
    from db_utils import get_db_conn
    from views import create_views
except ImportError as e:
    st.error(f"Failed to import database utilities from {PIPELINE_SRC}: {e}")
    st.stop()

# --- Page Configuration ---
st.set_page_config(
    page_title="Polydispute Dev UI",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("⚖️ Polydispute Data Exploration Tool")
st.caption("Internal development UI for inspecting Polymarket disputes, price swings, and voter calibrations.")


# --- Database Helpers with Caching ---
@st.cache_resource
def init_views_if_needed():
    """Ensure database views and macros are initialized."""
    conn = get_db_conn()
    try:
        create_views(conn)
    except Exception as e:
        st.warning(f"Note: Could not refresh views: {e}")
    finally:
        conn.close()


init_views_if_needed()


@st.cache_data(ttl=120)
def load_disputed_markets():
    """Query unique disputed markets with centralized latest stance per user per market_id."""
    conn = get_db_conn()
    query = """
    WITH market_thread_stats AS (
        SELECT 
            market_id,
            COUNT(DISTINCT thread_id) AS total_threads,
            COUNT(DISTINCT COALESCE(assertion_id, thread_id)) AS total_dispute_rounds
        FROM clean_dc_threads
        WHERE market_id IS NOT NULL
        GROUP BY market_id
    ),
    latest_market_threads AS (
        SELECT 
            market_id,
            thread_id,
            timestamp AS thread_created_at,
            ROW_NUMBER() OVER (PARTITION BY market_id ORDER BY timestamp DESC) AS rn
        FROM clean_dc_threads
        WHERE market_id IS NOT NULL
    ),
    user_latest_votes AS (
        SELECT 
            lt.market_id,
            msg.author_username,
            msg.vote_type,
            msg.timestamp,
            ROW_NUMBER() OVER (PARTITION BY lt.market_id, msg.author_username ORDER BY msg.timestamp DESC) AS rn
        FROM latest_market_threads lt
        JOIN clean_dc_messages msg ON lt.thread_id = msg.thread_id
        WHERE lt.rn = 1
          AND msg.vote_type IN ('P1', 'P2', 'P3', 'P4')
          AND msg.author_username NOT IN ('UMA Herald', 'UMA Heralds')
          AND LOWER(msg.author_username) NOT LIKE '%herald%'
    ),
    market_vote_aggregations AS (
        SELECT 
            market_id,
            COUNT(DISTINCT author_username) AS total_votes,
            COUNT(CASE WHEN vote_type = 'P1' THEN 1 END) AS p1_votes,
            COUNT(CASE WHEN vote_type = 'P2' THEN 1 END) AS p2_votes,
            COUNT(CASE WHEN vote_type = 'P3' THEN 1 END) AS p3_votes,
            COUNT(CASE WHEN vote_type = 'P4' THEN 1 END) AS p4_votes
        FROM user_latest_votes
        WHERE rn = 1
        GROUP BY market_id
    ),
    ur_latest AS (
        SELECT 
            question,
            ancillary_data,
            answer AS ur_answer,
            round_id AS ur_round_id,
            ROW_NUMBER() OVER (PARTITION BY question ORDER BY round_id DESC) AS rn
        FROM clean_ur_signals
    )
    SELECT 
        m.market_id,
        m.question,
        m.uma_resolution_status,
        m.closed,
        m.yes_price,
        m.no_price,
        COALESCE(dc.total_dispute_rounds, 1) AS total_rounds,
        COALESCE(dc.total_threads, 1) AS total_threads,
        CASE 
            WHEN ur.ur_answer IN ('P1', '1', 'NO') THEN 'NO'
            WHEN ur.ur_answer IN ('P2', '2', 'YES') THEN 'YES'
            WHEN ur.ur_answer IN ('P3', '3', '50/50') THEN '50-50'
            WHEN ur.ur_answer IN ('P4', '4', 'EARLY', 'TOO_EARLY', 'CANCEL') THEN 'TOO EARLY'
            ELSE COALESCE(ur.ur_answer, 'N/A')
        END AS ur_committee_signal,
        MAX(t.timestamp) AS dispute_start,
        MIN(t.timestamp) AS initial_dispute_start,
        m.closed_time,
        m.uma_end_date,
        COUNT(DISTINCT msg.message_id) AS total_messages,
        COALESCE(va.total_votes, 0) AS total_votes,
        COALESCE(va.p1_votes, 0) AS p1_votes,
        COALESCE(va.p2_votes, 0) AS p2_votes,
        COALESCE(va.p3_votes, 0) AS p3_votes,
        COALESCE(va.p4_votes, 0) AS p4_votes
    FROM clean_pm_markets m
    JOIN clean_dc_threads t ON m.market_id = t.market_id
    LEFT JOIN market_thread_stats dc ON m.market_id = dc.market_id
    LEFT JOIN market_vote_aggregations va ON m.market_id = va.market_id
    LEFT JOIN ur_latest ur ON (LOWER(TRIM(m.question)) = LOWER(TRIM(ur.question)) OR ur.ancillary_data LIKE '%' || m.market_id || '%') AND ur.rn = 1
    LEFT JOIN clean_dc_messages msg ON t.thread_id = msg.thread_id AND msg.author_username NOT IN ('UMA Herald', 'UMA Heralds')
    GROUP BY 
        m.market_id, m.question, m.uma_resolution_status, m.closed, 
        m.yes_price, m.no_price, dc.total_dispute_rounds, dc.total_threads,
        va.total_votes, va.p1_votes, va.p2_votes, va.p3_votes, va.p4_votes,
        ur.ur_answer, m.closed_time, m.uma_end_date
    ORDER BY MAX(t.timestamp) DESC;
    """
    try:
        df = conn.execute(query).df()
        return df
    finally:
        conn.close()


@st.cache_data(ttl=120)
def load_market_dispute_rounds(market_id: str):
    """
    Groups Discord messages for a market into distinct Dispute Rounds
    based on distinct thread/assertion entities.
    """
    conn = get_db_conn()
    query = f"""
    SELECT 
        t.thread_id,
        t.market_id,
        t.assertion_id,
        t.timestamp AS thread_created_at,
        m.message_id,
        m.author_username,
        m.timestamp,
        m.vote_type,
        m.content,
        m.urls
    FROM clean_dc_threads t
    LEFT JOIN clean_dc_messages m ON t.thread_id = m.thread_id
    WHERE t.market_id = '{market_id}'
      AND (m.author_username IS NULL OR (
           m.author_username NOT IN ('UMA Herald', 'UMA Heralds')
           AND LOWER(m.author_username) NOT LIKE '%herald%'
      ))
    ORDER BY t.timestamp ASC, m.timestamp ASC;
    """
    try:
        df = conn.execute(query).df()
        if df.empty:
            return pd.DataFrame(), []

        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df["thread_created_at"] = pd.to_datetime(df["thread_created_at"])

        # Group by thread_id ordered by thread creation time to assign round numbers
        unique_threads = df.sort_values("thread_created_at")["thread_id"].unique()
        thread_to_round = {tid: idx + 1 for idx, tid in enumerate(unique_threads)}
        df["round_num"] = df["thread_id"].map(thread_to_round)

        rounds_summary = []
        for r_num, group in df.groupby("round_num"):
            r_start = group["thread_created_at"].iloc[0]
            valid_msg_ts = group["timestamp"].dropna()
            r_end = valid_msg_ts.max() if not valid_msg_ts.empty else (r_start + pd.Timedelta(hours=48))
            threads = sorted(list(group["thread_id"].unique()))
            total_votes = len(group[group["vote_type"].isin(["P1", "P2", "P3", "P4"])])
            unique_voters = group["author_username"].dropna().nunique()
            assertion_ids = group["assertion_id"].dropna().unique()
            assertion_str = assertion_ids[0] if len(assertion_ids) > 0 else None

            rounds_summary.append({
                "round_num": int(r_num),
                "round_start": r_start,
                "round_end": r_end,
                "thread_ids": threads,
                "assertion_id": assertion_str,
                "total_votes": total_votes,
                "unique_voters": unique_voters,
            })

        return df, rounds_summary
    finally:
        conn.close()


@st.cache_data(ttl=120)
def load_market_price_history(market_id: str):
    """Query high-res price history for a specific market."""
    conn = get_db_conn()
    query = f"""
    SELECT 
        observed_at_iso AS timestamp,
        yes_price
    FROM raw_pm_price_history
    WHERE market_id = '{market_id}'
    ORDER BY observed_at ASC;
    """
    try:
        df = conn.execute(query).df()
        if not df.empty and "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"])
        return df
    finally:
        conn.close()


@st.cache_data(ttl=120)
def load_user_profiles(as_of: str | None = None):
    """Query user calibration profiles live or as-of a timestamp."""
    conn = get_db_conn()
    try:
        if as_of:
            query = f"""
            SELECT 
                author_username,
                total_predictions,
                gradeable_predictions,
                correct_predictions,
                lifetime_accuracy,
                is_calibrated,
                last_voted_at
            FROM fn_dc_user_profiles_as_of('{as_of}')
            ORDER BY gradeable_predictions DESC;
            """
        else:
            query = """
            SELECT 
                author_username,
                total_predictions,
                gradeable_predictions,
                correct_predictions,
                lifetime_accuracy,
                is_calibrated,
                last_voted_at
            FROM vw_dc_user_profiles
            ORDER BY gradeable_predictions DESC;
            """
        df = conn.execute(query).df()
        return df
    finally:
        conn.close()


# --- Sidebar Navigation ---
st.sidebar.header("Navigation & Settings")
tab_selection = st.sidebar.radio(
    "Select View",
    [
        "📊 Market Information & Arbitrage",
        "👤 Voter Calibration & Accuracy",
        "📖 Methodology & Backtest Validation",
    ],
)

st.sidebar.divider()
st.sidebar.subheader("Bayesian Accuracy Settings")
trust_number = st.sidebar.number_input(
    "Trust Number (N)",
    min_value=1,
    max_value=200,
    value=20,
    step=1,
    help="Pseudo-observations count representing confidence in the prior.",
)
prior_score = st.sidebar.number_input(
    "Prior Score (P)",
    min_value=0.0,
    max_value=1.0,
    value=0.50,
    step=0.05,
    help="Default accuracy prior for new / uncalibrated voters.",
)

st.sidebar.divider()
st.sidebar.subheader("Consensus Weighting Scheme")
weighting_mode = st.sidebar.selectbox(
    "Power Function",
    ["Quadratic (S² - Recommended)", "Linear (S)", "Cubic (S³)", "Custom Power (S^p)"],
    help="Determines how aggressively expert voters are amplified relative to low-accuracy voters.",
)
if weighting_mode == "Quadratic (S² - Recommended)":
    power_exponent = 2.0
elif weighting_mode == "Linear (S)":
    power_exponent = 1.0
elif weighting_mode == "Cubic (S³)":
    power_exponent = 3.0
else:
    power_exponent = st.sidebar.slider("Power Exponent (p)", min_value=0.5, max_value=5.0, value=2.0, step=0.1)

consensus_aggregation = st.sidebar.radio(
    "Voter Aggregation",
    ["Latest Stance per User (Unique Voters)", "Cumulative per Message"],
    help="Whether multiple messages from the same user update their stance or accumulate as independent votes.",
)

st.sidebar.divider()
st.sidebar.subheader("Voter Accuracy Exclusion Filter")
min_accuracy_filter = st.sidebar.slider(
    "Min Voter Accuracy (%)",
    min_value=0,
    max_value=95,
    value=0,
    step=5,
    help="Automatically excludes any voter whose historical accuracy is below this threshold from consensus EV calculations and time-series charts.",
)
min_accuracy_type = st.sidebar.selectbox(
    "Accuracy Filter Metric",
    ["Bayesian Accuracy (Recommended)", "Raw Lifetime Accuracy"],
    help="Whether to filter based on smoothed Empirical Bayes accuracy or raw historical win rate.",
)

# ==============================================================================
# TAB 1: MARKET INFORMATION & ARBITRAGE
# ==============================================================================
if tab_selection.startswith("📊 Market Information"):
    st.header("Disputed Markets & Trajectories")

    with st.spinner("Loading data from MotherDuck..."):
        markets_df = load_disputed_markets()
        users_raw_df = load_user_profiles()

    if markets_df.empty:
        st.warning("No disputed markets found in the database.")
        st.stop()

    # Build User Bayesian Score and Raw Accuracy lookup maps
    user_b_score_map = {}
    user_raw_acc_map = {}
    if not users_raw_df.empty:
        for _, u_row in users_raw_df.iterrows():
            uname = u_row["author_username"]
            g_preds = u_row["gradeable_predictions"] or 0
            c_preds = u_row["correct_predictions"] or 0.0
            raw_acc = u_row.get("lifetime_accuracy")
            # S = (P * N + C) / (N + G)
            b_score = ((prior_score * trust_number) + c_preds) / (trust_number + g_preds)
            user_b_score_map[uname] = b_score
            user_raw_acc_map[uname] = float(raw_acc) if pd.notnull(raw_acc) else prior_score

    def is_user_eligible(username: str) -> bool:
        """Checks if a user satisfies the minimum accuracy filter threshold."""
        if min_accuracy_filter <= 0:
            return True
        if min_accuracy_type.startswith("Bayesian"):
            acc = user_b_score_map.get(username, prior_score) * 100.0
        else:
            acc = user_raw_acc_map.get(username, prior_score) * 100.0
        return acc >= float(min_accuracy_filter)

    def get_user_power(username: str) -> tuple[float, float]:
        """Returns (bayesian_score, power_weight)."""
        score = user_b_score_map.get(username, prior_score)
        power = score ** power_exponent
        return score, power

    # --- Compute Market-Level Live Spread, Ground Truth & Lifecycle State ---
    def classify_ground_truth(row):
        closed = bool(row.get("closed", False))
        p_yes = row.get("yes_price")
        p_no = row.get("no_price")
        status = str(row.get("uma_resolution_status", "")).lower()
        ur_sig = str(row.get("ur_committee_signal", "")).upper()
        d_start = row.get("dispute_start")

        if pd.isna(p_yes):
            return "PENDING / UNKNOWN"

        p_yes = float(p_yes)
        p_no = float(p_no) if pd.notnull(p_no) else (1.0 - p_yes)

        # 1. Source A Ground Truth Rules (Polymarket Terminal Settlement)
        if p_yes >= 0.99:
            return "P2 (YES)"
        elif p_no >= 0.99 or p_yes <= 0.01:
            return "P1 (NO)"
        elif 0.48 <= p_yes <= 0.52 and (closed or status == "resolved"):
            return "P3 (50-50)"

        # 2. UMA Rocks Explicit P4 / Too Early Verdict
        if ur_sig in ["TOO EARLY", "P4", "CANCEL", "EARLY"]:
            return "P4 (Too Early)"

        # 3. Dispute Window Expiry (> 48h since dispute thread started)
        if pd.notnull(d_start):
            d_ts = pd.to_datetime(d_start)
            now_utc = pd.Timestamp.now(tz=d_ts.tzinfo if d_ts.tzinfo else None)
            hours_since = (now_utc - d_ts).total_seconds() / 3600.0
            if hours_since > 48.0 and not closed and (0.01 < p_yes < 0.99):
                return "P4 (Too Early)"

        if closed or status == "resolved":
            if p_yes > 0.60:
                return "P2 (YES)"
            elif p_yes < 0.40:
                return "P1 (NO)"
            else:
                return "P3 (50-50)"
        else:
            return "OPEN / PENDING"

    def classify_dispute_state(row):
        p_yes = row.get("yes_price")
        p_no = row.get("no_price")
        closed = bool(row.get("closed", False))
        status = str(row.get("uma_resolution_status", "")).lower()
        ur_sig = str(row.get("ur_committee_signal", "")).upper()
        d_start = row.get("dispute_start")

        if pd.notnull(p_yes):
            p_yes = float(p_yes)
            if p_yes >= 0.99:
                return "Resolved (YES - P2)"
            elif p_yes <= 0.01 or (pd.notnull(p_no) and float(p_no) >= 0.99):
                return "Resolved (NO - P1)"
            elif 0.48 <= p_yes <= 0.52 and (closed or status == "resolved"):
                return "Resolved (50-50 - P3)"

        if ur_sig in ["TOO EARLY", "P4", "CANCEL", "EARLY"]:
            return "Settled (Too Early - P4)"

        if pd.notnull(d_start):
            d_ts = pd.to_datetime(d_start)
            now_utc = pd.Timestamp.now(tz=d_ts.tzinfo if d_ts.tzinfo else None)
            hours_since = (now_utc - d_ts).total_seconds() / 3600.0
            if hours_since > 48.0 and not closed and (pd.isna(p_yes) or (0.01 < float(p_yes) < 0.99)):
                return "Settled (Too Early - P4)"
            elif hours_since <= 48.0:
                return "⚡ Live Active Dispute (≤ 48h)"

        if status == "disputed":
            return "⚡ Live Active Dispute (≤ 48h)"
        elif status == "proposed":
            return "Proposed"
        elif closed or status == "resolved":
            return "Resolved (Historical)"
        else:
            return "Open Trading"

    def classify_predominant_vote(row):
        p1 = row.get("p1_votes", 0) or 0
        p2 = row.get("p2_votes", 0) or 0
        p3 = row.get("p3_votes", 0) or 0
        total_v = p1 + p2 + p3
        if total_v == 0:
            return "NO VOTES"
        if p2 > p1 and p2 > p3:
            return "P2 (YES)"
        elif p1 > p2 and p1 > p3:
            return "P1 (NO)"
        elif p3 > p1 and p3 > p2:
            return "P3 (50-50)"
        else:
            return "TIE"

    def compute_row_spread(row):
        total_v = row.get("total_votes", 0) or 0
        p_yes = row.get("yes_price")
        if total_v == 0 or pd.isna(p_yes):
            return None, None, "No Votes / Price"

        p2 = row.get("p2_votes", 0) or 0
        p3 = row.get("p3_votes", 0) or 0
        p4 = row.get("p4_votes", 0) or 0
        price = float(p_yes)
        # Option 2: P1=0.0, P2=1.0, P3=0.50, P4=p_pre (anchored to baseline price)
        p_pre = price
        ev = (p2 * 1.0 + p3 * 0.50 + p4 * p_pre) / float(total_v)

        if ev > 0.50:
            spread = ev - price
            action = f"BUY YES ({spread * 100:+.1f}¢)" if spread > 0 else f"NO ARB ({spread * 100:+.1f}¢)"
        elif ev < 0.50:
            spread = price - ev
            action = f"BUY NO ({spread * 100:+.1f}¢)" if spread > 0 else f"NO ARB ({spread * 100:+.1f}¢)"
        else:
            spread = 0.0
            action = "NEUTRAL (0.0¢)"

        return ev, spread, action

    spread_metrics = [compute_row_spread(r) for _, r in markets_df.iterrows()]
    markets_df["crowd_ev"] = [m[0] for m in spread_metrics]
    markets_df["arb_spread"] = [m[1] for m in spread_metrics]
    markets_df["arb_spread_cents"] = [m[1] * 100.0 if m[1] is not None else None for m in spread_metrics]
    markets_df["arb_action"] = [m[2] for m in spread_metrics]

    markets_df["ground_truth"] = [classify_ground_truth(r) for _, r in markets_df.iterrows()]
    markets_df["dispute_state"] = [classify_dispute_state(r) for _, r in markets_df.iterrows()]
    markets_df["predominant_vote"] = [classify_predominant_vote(r) for _, r in markets_df.iterrows()]

    def classify_ev_call(ev):
        if ev is None or pd.isna(ev):
            return "NO VOTES"
        if ev > 0.55:
            return "P2 (YES)"
        elif ev < 0.45:
            return "P1 (NO)"
        else:
            return "P3 (50-50)"

    markets_df["ev_prediction"] = [classify_ev_call(ev) for ev in markets_df["crowd_ev"]]

    # Accuracy checks for resolved markets
    def check_pred_correct(row):
        gt = row["ground_truth"]
        pv = row["predominant_vote"]
        if gt not in ["P2 (YES)", "P1 (NO)", "P3 (50-50)"] or pv in ["NO VOTES", "TIE"]:
            return None
        return gt == pv

    def check_ev_correct(row):
        gt = row["ground_truth"]
        ev_call = row["ev_prediction"]
        if gt not in ["P2 (YES)", "P1 (NO)", "P3 (50-50)"] or ev_call == "NO VOTES":
            return None
        return gt == ev_call

    markets_df["is_pred_correct"] = [check_pred_correct(r) for _, r in markets_df.iterrows()]
    markets_df["is_ev_correct"] = [check_ev_correct(r) for _, r in markets_df.iterrows()]

    # --- 1. Aggregate Dispute Accuracy Scorecard (Source A Ground Truth) ---
    resolved_benchmark_df = markets_df[
        markets_df["ground_truth"].isin(["P2 (YES)", "P1 (NO)", "P3 (50-50)"])
        & (markets_df["total_votes"] > 0)
    ].copy()

    st.subheader("1. Aggregate Dispute Outcome Accuracy Benchmark")
    st.caption("Ground Truth is strictly determined from Source A (**Polymarket Terminal Settlement Prices**).")

    if not resolved_benchmark_df.empty:
        total_eval = len(resolved_benchmark_df)
        pred_valid = resolved_benchmark_df["is_pred_correct"].dropna()
        ev_valid = resolved_benchmark_df["is_ev_correct"].dropna()

        pred_correct_cnt = pred_valid.sum()
        pred_acc = (pred_correct_cnt / len(pred_valid) * 100.0) if len(pred_valid) > 0 else 0.0

        ev_correct_cnt = ev_valid.sum()
        ev_acc = (ev_correct_cnt / len(ev_valid) * 100.0) if len(ev_valid) > 0 else 0.0

        # Sub-group accuracy: YES vs NO
        yes_eval = resolved_benchmark_df[resolved_benchmark_df["ground_truth"] == "P2 (YES)"]
        yes_acc = (yes_eval["is_pred_correct"].sum() / len(yes_eval) * 100.0) if len(yes_eval) > 0 else 0.0

        no_eval = resolved_benchmark_df[resolved_benchmark_df["ground_truth"] == "P1 (NO)"]
        no_acc = (no_eval["is_pred_correct"].sum() / len(no_eval) * 100.0) if len(no_eval) > 0 else 0.0

        b_col1, b_col2, b_col3, b_col4 = st.columns(4)
        b_col1.metric("Resolved Markets Evaluated", f"{total_eval} Markets")
        b_col2.metric(
            "Predominant Plurality Accuracy",
            f"{pred_acc:.1f}%",
            delta=f"{pred_correct_cnt}/{len(pred_valid)} Correct",
        )
        b_col3.metric(
            "Weighted EV Implied Accuracy",
            f"{ev_acc:.1f}%",
            delta=f"{ev_correct_cnt}/{len(ev_valid)} Correct",
        )
        b_col4.metric(
            "Breakdown (YES / NO Truth)",
            f"{yes_acc:.0f}% / {no_acc:.0f}%",
            help=f"Accuracy on actual YES outcomes ({len(yes_eval)} markets) vs actual NO outcomes ({len(no_eval)} markets)",
        )

        with st.expander("📊 View Detailed Outcome Confusion Matrix & Accuracy Table", expanded=False):
            benchmark_table = resolved_benchmark_df[
                [
                    "market_id",
                    "question",
                    "ground_truth",
                    "predominant_vote",
                    "is_pred_correct",
                    "crowd_ev",
                    "ev_prediction",
                    "is_ev_correct",
                    "total_votes",
                ]
            ].copy()
            benchmark_table["Plurality Result"] = benchmark_table["is_pred_correct"].apply(
                lambda x: "✅ Correct" if x is True else ("❌ Incorrect" if x is False else "Tie / Ambiguous")
            )
            benchmark_table["EV Result"] = benchmark_table["is_ev_correct"].apply(
                lambda x: "✅ Correct" if x is True else ("❌ Incorrect" if x is False else "N/A")
            )
            st.dataframe(
                benchmark_table[
                    [
                        "market_id",
                        "question",
                        "ground_truth",
                        "predominant_vote",
                        "Plurality Result",
                        "crowd_ev",
                        "ev_prediction",
                        "EV Result",
                        "total_votes",
                    ]
                ].style.format({"crowd_ev": "${:.3f}", "total_votes": "{:.0f}"}),
                use_container_width=True,
                hide_index=True,
            )
    else:
        st.info("No resolved disputed markets with recorded votes currently available for benchmarking.")

    st.divider()

    # --- Markets Summary Table ---
    st.subheader("2. Disputed Threads & Arbitrage Catalog")

    # Filter controls
    col_f1, col_f2, col_f3, col_f4, col_f5 = st.columns([2, 1.3, 1, 1, 0.8])
    with col_f1:
        search_query = st.text_input("🔍 Search Question or Market ID", "")
    with col_f2:
        state_filter = st.selectbox(
            "Dispute Lifecycle State",
            ["All"] + sorted(list(markets_df["dispute_state"].dropna().unique())),
        )
    with col_f3:
        only_live_disputes = st.checkbox("⚡ Live Only (≤ 48h)", value=False, help="Filter to only markets where dispute window started within the past 48 hours.")
    with col_f4:
        only_arb = st.checkbox("🟢 Arbitrage Only (Spread > 0)", value=False)
    with col_f5:
        min_votes_filter = st.number_input("Min Votes", min_value=0, value=0, step=1)

    filtered_df = markets_df.copy()
    if search_query:
        filtered_df = filtered_df[
            filtered_df["question"].str.contains(search_query, case=False, na=False)
            | filtered_df["market_id"].str.contains(search_query, case=False, na=False)
        ]
    if state_filter != "All":
        filtered_df = filtered_df[filtered_df["dispute_state"] == state_filter]
    if only_live_disputes:
        filtered_df = filtered_df[filtered_df["dispute_state"].str.contains("Live", case=False, na=False)]
    if only_arb:
        filtered_df = filtered_df[filtered_df["arb_spread"] > 0]
    if min_votes_filter > 0:
        filtered_df = filtered_df[filtered_df["total_votes"] >= min_votes_filter]

    # Sort by Arbitrage Spread descending
    filtered_df = filtered_df.sort_values("arb_spread", ascending=False, na_position="last")

    st.caption("💡 *Click on any row in the table below to immediately inspect its deep-dive charts & trajectory.*")

    catalog_display_df = filtered_df[
        [
            "market_id",
            "question",
            "dispute_state",
            "ground_truth",
            "ur_committee_signal",
            "yes_price",
            "crowd_ev",
            "predominant_vote",
            "arb_spread_cents",
            "arb_action",
            "total_votes",
            "total_rounds",
            "total_threads",
            "dispute_start",
            "closed_time",
        ]
    ].rename(columns={"ur_committee_signal": "UR Committee Submit"}).reset_index(drop=True)

    selection_event = st.dataframe(
        catalog_display_df.style.format(
            {
                "yes_price": "${:.3f}",
                "crowd_ev": "${:.3f}",
                "arb_spread_cents": "{:+.1f}¢",
                "total_votes": "{:.0f}",
            }
        ),
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
    )

    st.divider()

    # --- Market Detail & Plot Selection ---
    st.subheader("3. Market Deep-Dive & Trajectory Plots")

    market_options = filtered_df["market_id"].tolist()
    if not market_options:
        st.info("No markets match the current search filter.")
        st.stop()

    # Determine selected market from row click or fallback
    clicked_market_id = None
    if selection_event and hasattr(selection_event, "selection") and selection_event.selection.rows:
        clicked_idx = selection_event.selection.rows[0]
        if clicked_idx < len(catalog_display_df):
            clicked_market_id = catalog_display_df.iloc[clicked_idx]["market_id"]

    default_idx = 0
    if clicked_market_id and clicked_market_id in market_options:
        default_idx = market_options.index(clicked_market_id)

    def format_market_option(m_id):
        row = filtered_df[filtered_df["market_id"] == m_id].iloc[0]
        q = row["question"]
        status = row["uma_resolution_status"] or "unknown"
        ur_sig = row.get("ur_committee_signal") or "N/A"
        rounds = int(row.get("total_rounds", 1))
        threads = int(row.get("total_threads", 1))
        action = row.get("arb_action", "")
        if threads > 1 and rounds == 1:
            round_badge = f"[1 Dispute ({threads} Threads)]"
        else:
            round_badge = f"[{rounds} Dispute{'s' if rounds > 1 else ''}]"
        return f"[{m_id}] {round_badge} [UR: {ur_sig}] [{action}] ({status}) {q[:55]}..."

    selected_market_id = st.selectbox(
        "Active Market Selection (Click a table row above or choose here):",
        options=market_options,
        index=default_idx,
        format_func=format_market_option,
    )

    selected_row = filtered_df[filtered_df["market_id"] == selected_market_id].iloc[0]

    # Load Clustered Dispute Rounds for this Market
    all_msgs_df, rounds_summary = load_market_dispute_rounds(selected_market_id)
    total_rounds_count = len(rounds_summary)

    # Key Metrics Cards
    m_col1, m_col2, m_col3, m_col4, m_col5 = st.columns(5)
    m_col1.metric("Market ID", selected_market_id)
    m_col2.metric("Dispute State", str(selected_row.get("dispute_state", selected_row.get("uma_resolution_status", "N/A"))).upper())
    m_col3.metric("UR Committee Submit", str(selected_row.get("ur_committee_signal") or "N/A").upper())
    m_col4.metric(
        "Current YES / NO Price",
        f"${selected_row['yes_price']:.3f} / ${selected_row['no_price']:.3f}"
        if pd.notnull(selected_row["yes_price"])
        else "N/A",
    )
    m_col5.metric("Dispute Rounds", f"{total_rounds_count} Round(s)")

    # Exclusively consider and process the LATEST dispute round
    if rounds_summary:
        latest_round = rounds_summary[-1]
        latest_round_num = latest_round["round_num"]
        votes_df = all_msgs_df[
            (all_msgs_df["round_num"] == latest_round_num)
            & all_msgs_df["vote_type"].isin(["P1", "P2", "P3", "P4"])
        ].copy()
        view_label = f"Dispute Round {latest_round_num} (Latest)"
    else:
        latest_round = None
        latest_round_num = 1
        votes_df = all_msgs_df[all_msgs_df["vote_type"].isin(["P1", "P2", "P3", "P4"])].copy() if not all_msgs_df.empty else pd.DataFrame()
        view_label = "Dispute Round 1"

    if total_rounds_count > 1 and latest_round:
        st.info(
            f"🔔 **Multi-Round Dispute Detected ({total_rounds_count} Rounds):** "
            f"Calculations, crowd EV, and trajectory curves are strictly displaying the **Latest Dispute Round (Round {latest_round_num})** "
            f"started on {latest_round['round_start'].strftime('%Y-%m-%d %H:%M UTC')}"
            + (f" (Assertion: `{latest_round['assertion_id'][:12]}...`)" if latest_round.get("assertion_id") else "")
            + f" with {latest_round['total_votes']} votes."
        )

    # Apply Voter Accuracy Exclusion Filter
    if not votes_df.empty and min_accuracy_filter > 0:
        orig_votes_cnt = len(votes_df)
        orig_users_cnt = votes_df["author_username"].nunique()
        votes_df = votes_df[votes_df["author_username"].apply(is_user_eligible)].copy()
        excluded_votes_cnt = orig_votes_cnt - len(votes_df)
        remaining_users_cnt = votes_df["author_username"].nunique()
        if excluded_votes_cnt > 0:
            st.info(
                f"🎯 **Accuracy Filter Active (≥ {min_accuracy_filter}% {min_accuracy_type}):** "
                f"Retained **{remaining_users_cnt}/{orig_users_cnt} voters** ({len(votes_df)}/{orig_votes_cnt} votes). "
                f"Excluded {excluded_votes_cnt} votes from voters below the accuracy threshold."
            )

    with st.expander("Full Market Question & Metadata", expanded=False):
        st.write(f"**Question:** {selected_row['question']}")
        st.write(f"**Dispute Rounds Detected:** {total_rounds_count}")
        st.write(f"**First Dispute Started At:** {selected_row['dispute_start']}")
        st.write(f"**Market Closed At:** {selected_row['closed_time']}")
        st.write(f"**UMA End Date:** {selected_row['uma_end_date']}")
        if rounds_summary:
            st.markdown("**Dispute Rounds Summary:**")
            st.dataframe(pd.DataFrame(rounds_summary), use_container_width=True, hide_index=True)

    # Load Price History
    price_df = load_market_price_history(selected_market_id)

    vote_types = ["P1", "P2", "P3", "P4"]
    vote_labels = {
        "P1": "P1 (NO)",
        "P2": "P2 (YES)",
        "P3": "P3 (50-50)",
        "P4": "P4 (Too Early / Prov. NO)",
    }
    colors = {
        "P1": "#d62728",  # Red
        "P2": "#2ca02c",  # Green
        "P3": "#ff7f0e",  # Orange
        "P4": "#9467bd",  # Purple
    }

    # Helper for point-in-time price lookup
    def get_price_at_timestamp(ts, p_df, fallback_val=0.50):
        if p_df is None or p_df.empty:
            return fallback_val
        ts_comp = ts
        if ts.tzinfo is None and p_df["timestamp"].dt.tz is not None:
            ts_comp = ts.tz_localize("UTC")
        elif ts.tzinfo is not None and p_df["timestamp"].dt.tz is None:
            ts_comp = ts.tz_localize(None)

        sub = p_df[p_df["timestamp"] <= ts_comp]
        if not sub.empty:
            return float(sub.iloc[-1]["yes_price"])
        return float(p_df.iloc[0]["yes_price"])

    # Process Vote Time Series (Raw & Bayesian Weighted)
    has_votes = not votes_df.empty
    if has_votes:
        votes_df = votes_df.sort_values("timestamp").reset_index(drop=True)

        # Attach scores & power weights to each voting event
        votes_df["bayesian_score"] = votes_df["author_username"].apply(lambda u: get_user_power(u)[0])
        votes_df["power_weight"] = votes_df["author_username"].apply(lambda u: get_user_power(u)[1])

        fallback_m_price = float(selected_row["yes_price"]) if pd.notnull(selected_row.get("yes_price")) else 0.50

        # Compute Time Series
        records = []
        user_stances = {}  # username -> (vote_type, power, payoff)

        # Accumulators for "Cumulative per Message" mode
        cum_counts = {vt: 0 for vt in vote_types}
        cum_weights = {vt: 0.0 for vt in vote_types}
        cum_w_payoff = 0.0
        cum_r_payoff = 0.0

        for _, row in votes_df.iterrows():
            ts = row["timestamp"]
            vtype = row["vote_type"]
            uname = row["author_username"]
            b_score = row["bayesian_score"]
            weight = row["power_weight"]

            # Payoff assignment: P1=0.0, P2=1.0, P3=0.50, P4=price immediately before this vote
            if vtype == "P1":
                payoff = 0.0
            elif vtype == "P2":
                payoff = 1.0
            elif vtype == "P3":
                payoff = 0.50
            elif vtype == "P4":
                payoff = get_price_at_timestamp(ts, price_df, fallback_val=fallback_m_price)
            else:
                payoff = 0.50

            if consensus_aggregation.startswith("Latest Stance"):
                user_stances[uname] = (vtype, weight, payoff)

                # Sum active stances
                v_counts = {vt: 0 for vt in vote_types}
                v_weights = {vt: 0.0 for vt in vote_types}
                sum_w_payoff = 0.0
                sum_r_payoff = 0.0
                for u_vtype, u_weight, u_payoff in user_stances.values():
                    v_counts[u_vtype] += 1
                    v_weights[u_vtype] += u_weight
                    sum_w_payoff += (u_weight * u_payoff)
                    sum_r_payoff += (1.0 * u_payoff)
            else:
                cum_counts[vtype] += 1
                cum_weights[vtype] += weight
                cum_w_payoff += (weight * payoff)
                cum_r_payoff += (1.0 * payoff)
                v_counts = dict(cum_counts)
                v_weights = dict(cum_weights)
                sum_w_payoff = cum_w_payoff
                sum_r_payoff = cum_r_payoff

            total_raw = sum(v_counts.values())
            total_weighted = sum(v_weights.values())

            rec = {
                "timestamp": ts,
                "author": uname,
                "vote_type": vtype,
                "score": b_score,
                "weight": weight,
                "payoff": payoff,
                "weighted_implied_ev": (sum_w_payoff / total_weighted) if total_weighted > 0 else 0.50,
                "raw_implied_ev": (sum_r_payoff / total_raw) if total_raw > 0 else 0.50,
            }
            for vt in vote_types:
                rec[f"{vt}_raw_cnt"] = v_counts[vt]
                rec[f"{vt}_raw_pct"] = (v_counts[vt] / total_raw * 100.0) if total_raw > 0 else 0.0
                rec[f"{vt}_weighted_val"] = v_weights[vt]
                rec[f"{vt}_weighted_pct"] = (v_weights[vt] / total_weighted * 100.0) if total_weighted > 0 else 0.0

            records.append(rec)

        consensus_ts_df = pd.DataFrame(records)

        # Extend stepped time-series to latest price observation if available
        if not consensus_ts_df.empty and not price_df.empty:
            t_last_vote = consensus_ts_df["timestamp"].iloc[-1]
            t_last_price = price_df["timestamp"].max()
            if t_last_vote.tzinfo is None and t_last_price.tzinfo is not None:
                t_last_vote_comp = t_last_vote.tz_localize("UTC")
            else:
                t_last_vote_comp = t_last_vote
            if t_last_price.tzinfo is None and t_last_vote.tzinfo is not None:
                t_last_price_comp = t_last_price.tz_localize("UTC")
            else:
                t_last_price_comp = t_last_price

            if t_last_price_comp > t_last_vote_comp:
                last_rec = consensus_ts_df.iloc[-1].to_dict()
                last_rec["timestamp"] = t_last_price
                consensus_ts_df = pd.concat([consensus_ts_df, pd.DataFrame([last_rec])], ignore_index=True)

    # --- Trajectory & Consensus Graphs (Stacked Vertical Layout) ---
    st.markdown("### 3. Trajectory & Consensus Graphs")

    # 1. Top Chart: Full Lifecycle Polymarket YES Price
    st.markdown("#### 📈 1. Full Polymarket Price History (Market Inception to Resolution)")
    if price_df.empty:
        st.info("No CLOB price history recorded for this market.")
    else:
        fig_top, ax_top = plt.subplots(figsize=(12, 3.5))
        ax_top.plot(
            price_df["timestamp"],
            price_df["yes_price"],
            color="#1f77b4",
            linewidth=2.0,
            label="Polymarket YES Midpoint Price",
        )

        # Highlight Clustered Dispute Windows on the Top Price Chart
        round_palette = ["#e53935", "#8e24aa", "#f57c00", "#00897b"]
        line_palette = ["#d32f2f", "#6a1b9a", "#e65100", "#004d40"]

        if rounds_summary:
            for idx, r in enumerate(rounds_summary):
                t_r_start = r["round_start"]
                # Cap the dispute window to max 48 hours
                t_r_end = min(
                    r["round_end"] + pd.Timedelta(hours=2),
                    t_r_start + pd.Timedelta(hours=48),
                )
                if t_r_end <= t_r_start:
                    t_r_end = t_r_start + pd.Timedelta(hours=48)

                # Ensure timezone compatibility
                if t_r_start.tzinfo is None and price_df["timestamp"].dt.tz is not None:
                    t_r_start = t_r_start.tz_localize("UTC")
                if t_r_end.tzinfo is None and price_df["timestamp"].dt.tz is not None:
                    t_r_end = t_r_end.tz_localize("UTC")

                is_latest_r = (idx == len(rounds_summary) - 1)
                shade_color = "#e53935" if is_latest_r else "#9e9e9e"
                line_color = "#d32f2f" if is_latest_r else "#757575"
                alpha_val = 0.22 if is_latest_r else 0.08
                r_tag = "Latest" if is_latest_r else "Historical"

                ax_top.axvspan(
                    t_r_start,
                    t_r_end,
                    color=shade_color,
                    alpha=alpha_val,
                    label=f"Round {r['round_num']} ({r_tag}: {t_r_start.strftime('%m/%d %H:%M')} – {t_r_end.strftime('%m/%d %H:%M')})",
                )
                ax_top.axvline(
                    t_r_start,
                    color=line_color,
                    linestyle="-" if is_latest_r else ":",
                    linewidth=2.0 if is_latest_r else 1.2,
                    alpha=0.9 if is_latest_r else 0.6,
                    label=f"Round {r['round_num']} Start ({r_tag})",
                )
        elif pd.notnull(selected_row.get("dispute_start")):
            t_r_start = pd.to_datetime(selected_row["dispute_start"])
            t_r_end = t_r_start + pd.Timedelta(hours=48)
            if t_r_start.tzinfo is None and price_df["timestamp"].dt.tz is not None:
                t_r_start = t_r_start.tz_localize("UTC")
            if t_r_end.tzinfo is None and price_df["timestamp"].dt.tz is not None:
                t_r_end = t_r_end.tz_localize("UTC")
            ax_top.axvspan(
                t_r_start,
                t_r_end,
                color=round_palette[0],
                alpha=0.18,
                label=f"Dispute Window ({t_r_start.strftime('%m/%d %H:%M')} – {t_r_end.strftime('%m/%d %H:%M')})",
            )
            ax_top.axvline(
                t_r_start,
                color=line_palette[0],
                linestyle="--",
                linewidth=1.8,
                alpha=0.85,
                label="Dispute Start",
            )

        ax_top.set_ylim(-0.05, 1.05)
        ax_top.set_ylabel("Price (USD)")
        ax_top.set_xlabel("Time (UTC)")
        ax_top.grid(True, linestyle="--", alpha=0.5)
        ax_top.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d %H:%M"))
        fig_top.autofmt_xdate()
        ax_top.legend(loc="upper left", frameon=True, fontsize=8.5)
        st.pyplot(fig_top)
        plt.close(fig_top)

    st.markdown("<br>", unsafe_allow_html=True)

    # 2. Bottom Chart: Dispute Window Overlay (Weighted Consensus + YES Price)
    power_label = "S²" if power_exponent == 2.0 else f"S^{power_exponent:g}"
    st.markdown(f"#### 🗳️ 2. Dispute Window ({view_label}): Calibration-Weighted Consensus ({power_label}) & YES Price Overlay")

    if not has_votes:
        st.info("No DVM votes recorded in this thread yet.")
    else:
        fig_bot, ax_left = plt.subplots(figsize=(12, 5.2))
        ax_right = ax_left.twinx()  # Secondary y-axis for YES Price

        # A. Plot Left Axis: Calibration-Weighted Consensus Shares (%)
        for vt in vote_types:
            if consensus_ts_df[f"{vt}_raw_cnt"].iloc[-1] > 0:
                final_w_pct = consensus_ts_df[f"{vt}_weighted_pct"].iloc[-1]

                # Stepped line for Bayesian Weighted Share (updates at moment vote is cast)
                ax_left.plot(
                    consensus_ts_df["timestamp"],
                    consensus_ts_df[f"{vt}_weighted_pct"],
                    color=colors[vt],
                    linestyle="-",
                    drawstyle="steps-post",
                    linewidth=2.4,
                    label=f"{vote_labels[vt]} (Weighted: {final_w_pct:.1f}%)",
                )

        ax_left.set_ylim(-5, 105)
        ax_left.set_ylabel("Weighted Consensus Share (%)", color="#2c3e50", fontsize=11, fontweight="bold")
        ax_left.set_xlabel("Time (UTC)", fontsize=10)
        ax_left.grid(True, linestyle="--", alpha=0.4)

        # B. Plot Right Axis: Dispute Window YES Price
        if not price_df.empty:
            t_min = consensus_ts_df["timestamp"].min()
            t_max = consensus_ts_df["timestamp"].max()
            padding = pd.Timedelta(hours=4)

            disp_price_df = price_df[
                (price_df["timestamp"] >= t_min - padding) & (price_df["timestamp"] <= t_max + padding)
            ]
            if disp_price_df.empty:
                disp_price_df = price_df

            ax_right.plot(
                disp_price_df["timestamp"],
                disp_price_df["yes_price"],
                color="#000000",
                linestyle="-",
                linewidth=1.2,
                label="YES Price (Dispute Window)",
                alpha=0.85,
            )
            ax_right.set_ylim(-0.05, 1.05)
            ax_right.set_ylabel("Polymarket YES Price ($)", color="#111111", fontsize=11, fontweight="bold")
            ax_right.tick_params(axis="y", labelcolor="#111111")

        ax_left.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
        fig_bot.autofmt_xdate()

        # Combine Legends from both axes
        lines_l, labels_l = ax_left.get_legend_handles_labels()
        lines_r, labels_r = ax_right.get_legend_handles_labels()
        ax_left.legend(
            lines_l + lines_r,
            labels_l + labels_r,
            loc="upper left",
            bbox_to_anchor=(1.08, 1.0),
            fontsize=8.5,
            frameon=True,
        )
        st.pyplot(fig_bot, bbox_inches="tight")
        plt.close(fig_bot)

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown(f"#### 🎯 3. Unified Price & Crowd Implied Value (EV) Overlay ({view_label})")
        st.caption(
            "Direct comparison on a unified $0.00–$1.00 scale: "
            "**Calibration-Weighted EV** (Solid Green) vs. **Orderbook YES Price** (Solid Black). "
            "P4 (Too Early) votes contribute the point-in-time market YES price observed immediately prior to each vote."
        )

        final_w_ev = consensus_ts_df["weighted_implied_ev"].iloc[-1]

        fig_ev, ax_ev = plt.subplots(figsize=(12, 4.5))

        # Line 1: Calibration-Weighted Crowd Implied EV (Stepped Line)
        ax_ev.plot(
            consensus_ts_df["timestamp"],
            consensus_ts_df["weighted_implied_ev"],
            color="#2e7d32",
            linestyle="-",
            drawstyle="steps-post",
            linewidth=2.5,
            label=f"Calibration-Weighted Implied EV ({power_label}): ${final_w_ev:.3f}",
            zorder=3,
        )

        # Plot discrete marker dots at exact vote event timestamps
        vote_ev_pts = consensus_ts_df.iloc[:-1] if len(consensus_ts_df) > 1 else consensus_ts_df
        for _, pt in vote_ev_pts.iterrows():
            vt = pt.get("vote_type")
            uname = pt.get("author", "")
            if vt in colors:
                ax_ev.scatter(
                    pt["timestamp"],
                    pt["weighted_implied_ev"],
                    color=colors[vt],
                    s=40,
                    edgecolors="#111",
                    linewidth=0.8,
                    zorder=5,
                )

        # Line 3: Polymarket Orderbook YES Price
        if not price_df.empty:
            t_min = consensus_ts_df["timestamp"].min()
            t_max = consensus_ts_df["timestamp"].max()
            padding = pd.Timedelta(hours=4)

            disp_price_df = price_df[
                (price_df["timestamp"] >= t_min - padding) & (price_df["timestamp"] <= t_max + padding)
            ]
            if disp_price_df.empty:
                disp_price_df = price_df

            final_m_price = disp_price_df["yes_price"].iloc[-1] if not disp_price_df.empty else 0.0

            ax_ev.plot(
                disp_price_df["timestamp"],
                disp_price_df["yes_price"],
                color="#000000",
                linestyle="-",
                linewidth=1.5,
                label=f"Polymarket YES Price (Orderbook): ${final_m_price:.3f}",
                alpha=0.9,
            )
        else:
            final_m_price = selected_row["yes_price"] if pd.notnull(selected_row["yes_price"]) else 0.0

        # Reference line at $0.50
        ax_ev.axhline(0.50, color="#9e9e9e", linestyle=":", linewidth=1.0, alpha=0.6, label="50/50 Baseline ($0.50)")

        ax_ev.set_ylim(-0.05, 1.05)
        ax_ev.set_ylabel("Price / Implied Value (USD)", fontsize=11, fontweight="bold")
        ax_ev.set_xlabel("Time (UTC)", fontsize=10)
        ax_ev.grid(True, linestyle="--", alpha=0.4)
        ax_ev.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
        fig_ev.autofmt_xdate()
        ax_ev.legend(loc="upper left", bbox_to_anchor=(1.01, 1.0), fontsize=8.5, frameon=True)
        st.pyplot(fig_ev, bbox_inches="tight")
        plt.close(fig_ev)

        # Polarized Arbitrage Spread Calculation
        if final_w_ev > 0.50:
            arb_dir = "BUY YES"
            live_spread = final_w_ev - final_m_price
            edge_desc = f"Crowd leans **YES (${final_w_ev:.3f})** vs Market **${final_m_price:.3f}**. Edge: **{live_spread * 100:+.1f}¢** on YES."
        elif final_w_ev < 0.50:
            arb_dir = "BUY NO"
            live_spread = final_m_price - final_w_ev
            edge_desc = f"Crowd leans **NO (Implied YES ${final_w_ev:.3f})** vs Market **${final_m_price:.3f}**. Edge: **{live_spread * 100:+.1f}¢** on NO."
        else:
            arb_dir = "NEUTRAL"
            live_spread = 0.0
            edge_desc = "Crowd is neutral at $0.50 (50-50 / Ambiguous consensus)."

        # Mispricing Spread Metric Cards
        ev_col1, ev_col2, ev_col3 = st.columns(3)
        ev_col1.metric("Calibration-Weighted Crowd EV", f"${final_w_ev:.3f}")
        ev_col2.metric("Polymarket Orderbook Price", f"${final_m_price:.3f}" if pd.notnull(final_m_price) else "N/A")
        ev_col3.metric(
            f"Arbitrage Action: {arb_dir}",
            f"{live_spread * 100:+.1f}¢",
            delta=f"{live_spread:+.3f} USD Spread",
        )

        if live_spread > 0.02:
            st.success(f"🟢 **Actionable Arbitrage Opportunity ({arb_dir}):** {edge_desc}")
        elif live_spread < -0.02:
            st.info(f"⚪ **No Arbitrage ({arb_dir}):** Market orderbook is pricing more aggressively than crowd consensus ({live_spread * 100:.1f}¢ spread).")
        else:
            st.warning(f"🟡 **Market Fairly Priced:** Crowd EV and orderbook price are in near-equilibrium ({live_spread * 100:+.1f}¢ spread).")

        st.divider()

        # C. Summary Comparison Table & Highlights
        col_sum1, col_sum2 = st.columns([3, 2])
        with col_sum1:
            st.markdown("#### ⚖️ Final Consensus Breakdown (Raw vs. Weighted)")
            last_rec = consensus_ts_df.iloc[-1]
            dist_data = []
            for vt in vote_types:
                dist_data.append({
                    "Outcome Option": vote_labels[vt],
                    "Raw Count": int(last_rec[f"{vt}_raw_cnt"]),
                    "Raw Share (%)": f"{last_rec[f'{vt}_raw_pct']:.1f}%",
                    f"Weighted Sum ({power_label})": f"{last_rec[f'{vt}_weighted_val']:.2f}",
                    "Weighted Consensus (%)": f"{last_rec[f'{vt}_weighted_pct']:.1f}%",
                })
            summary_table_df = pd.DataFrame(dist_data)
            st.table(summary_table_df)

        with col_sum2:
            st.markdown("#### 🎯 Leading Consensus Callout")
            weighted_pcts = {vt: last_rec[f"{vt}_weighted_pct"] for vt in vote_types}
            winner_vt = max(weighted_pcts, key=weighted_pcts.get)
            winner_pct = weighted_pcts[winner_vt]
            raw_pct = last_rec[f"{winner_vt}_raw_pct"]

            if winner_pct > 0:
                st.success(
                    f"### {vote_labels[winner_vt]}\n"
                    f"- **Weighted Power:** {winner_pct:.1f}% of total score\n"
                    f"- **Raw Vote Share:** {raw_pct:.1f}% ({int(last_rec[f'{winner_vt}_raw_cnt'])} votes)\n"
                    f"- **Weight Scheme:** {weighting_mode}"
                )

        st.divider()

        # D. Voter Accuracy Distribution Dot Map (Who is backing each side)
        st.markdown("#### 👥 4. Voter Accuracy Distribution Dot Map")
        st.caption(
            "Each dot represents an individual unique voter. Vertical position represents their historical Bayesian accuracy. "
            f"Solid black bars indicate the **Power-Mean (RMS Average for {power_label})** accuracy of that cohort."
        )

        # Dedup to latest stance per user for the dot map
        dot_df = votes_df.sort_values("timestamp").groupby("author_username").last().reset_index()

        if not dot_df.empty:
            fig_dot, ax_dot = plt.subplots(figsize=(10, 4.2))

            import hashlib

            def get_jitter(name: str) -> float:
                h = int(hashlib.md5(name.encode("utf-8")).hexdigest()[:8], 16)
                return ((h % 1000) / 500.0 - 1.0) * 0.16

            x_indices = {vt: idx for idx, vt in enumerate(vote_types)}

            for _, v_row in dot_df.iterrows():
                vt = v_row["vote_type"]
                if vt in x_indices:
                    x_pos = x_indices[vt] + get_jitter(v_row["author_username"])
                    y_pos = v_row["bayesian_score"] * 100.0
                    ax_dot.scatter(
                        x_pos,
                        y_pos,
                        s=25,
                        color=colors[vt],
                        alpha=0.85,
                        edgecolors="#222222",
                        linewidth=0.8,
                        zorder=4,
                    )

            # Draw Power-Mean (RMS / Generalized Mean) accuracy bars and count annotations
            p_exp = float(power_exponent)
            for vt in vote_types:
                x_idx = x_indices[vt]
                cohort = dot_df[dot_df["vote_type"] == vt]
                if not cohort.empty:
                    # Generalized p-power mean matching the weighting exponent
                    rms_acc = ((cohort["bayesian_score"] ** p_exp).mean() ** (1.0 / p_exp)) * 100.0
                    ax_dot.hlines(
                        rms_acc,
                        x_idx - 0.28,
                        x_idx + 0.28,
                        colors="black",
                        linewidth=2.5,
                        linestyles="-",
                        zorder=5,
                    )
                    ax_dot.text(
                        x_idx,
                        103,
                        f"n={len(cohort)}\nAvg: {rms_acc:.1f}%",
                        ha="center",
                        va="bottom",
                        fontsize=9,
                        fontweight="bold",
                        bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.85, edgecolor="#bbb"),
                    )

            ax_dot.axhline(
                prior_score * 100.0,
                color="#757575",
                linestyle="--",
                linewidth=1.2,
                alpha=0.7,
                label=f"Prior Baseline ({prior_score*100:.0f}%)",
                zorder=2,
            )

            ax_dot.set_xticks(range(len(vote_types)))
            ax_dot.set_xticklabels([vote_labels[vt] for vt in vote_types], fontsize=10, fontweight="bold")
            ax_dot.set_ylabel("Voter Accuracy Score (%)", fontsize=10, fontweight="bold")
            ax_dot.set_ylim(0, 118)
            ax_dot.grid(axis="y", linestyle="--", alpha=0.4, zorder=1)
            ax_dot.legend(loc="lower right", frameon=True, fontsize=8.5)

            st.pyplot(fig_dot, bbox_inches="tight")
            plt.close(fig_dot)

        # E. Detailed Vote Stream Expander
        with st.expander("Show Detailed Vote Data Table", expanded=False):
            st.dataframe(
                votes_df[["timestamp", "author_username", "vote_type", "bayesian_score", "power_weight"]].rename(
                    columns={
                        "author_username": "Voter",
                        "vote_type": "Vote",
                        "bayesian_score": "Bayesian Score (S)",
                        "power_weight": f"Weight ({power_label})",
                    }
                ).style.format({"Bayesian Score (S)": "{:.2%}", f"Weight ({power_label})": "{:.3f}"}),
                use_container_width=True,
                hide_index=True,
            )

        st.divider()

        # F. Chronological Chat & Reasoning Stream
        st.markdown("#### 💬 5. Dispute Chat & Vote Reasoning Stream")
        st.caption("Chronological stream of Discord messages, reasoning, and evidence posted during this dispute round.")

        msg_filter_col1, msg_filter_col2 = st.columns([1, 2])
        with msg_filter_col1:
            chat_vtype_filter = st.selectbox(
                "Filter by Stance",
                ["All Stances", "P1 (NO)", "P2 (YES)", "P3 (50-50)", "P4 (Too Early)"],
            )
        with msg_filter_col2:
            chat_search = st.text_input("🔍 Search message content or author", "")

        # Filter messages
        chat_display_df = votes_df.copy() if not votes_df.empty else pd.DataFrame()
        if not chat_display_df.empty:
            if chat_vtype_filter != "All Stances":
                selected_vt = chat_vtype_filter.split(" ")[0]
                chat_display_df = chat_display_df[chat_display_df["vote_type"] == selected_vt]
            if chat_search:
                chat_display_df = chat_display_df[
                    chat_display_df["author_username"].str.contains(chat_search, case=False, na=False)
                    | chat_display_df["content"].fillna("").str.contains(chat_search, case=False, na=False)
                ]

            if chat_display_df.empty:
                st.info("No messages match the current chat filter.")
            else:
                for _, m_row in chat_display_df.iterrows():
                    vt = m_row["vote_type"]
                    uname = m_row["author_username"]
                    b_score = m_row.get("bayesian_score", 0.50)
                    p_weight = m_row.get("power_weight", 0.25)
                    msg_ts = m_row["timestamp"].strftime("%Y-%m-%d %H:%M UTC") if pd.notnull(m_row["timestamp"]) else "N/A"
                    content_text = m_row.get("content") or "*(No text content provided)*"
                    urls_list = m_row.get("urls")

                    # Stance color pill
                    v_badge = {
                        "P1": "🔴 **P1 (NO)**",
                        "P2": "🟢 **P2 (YES)**",
                        "P3": "🟠 **P3 (50-50)**",
                        "P4": "🟣 **P4 (Too Early)**",
                    }.get(vt, f"⚪ **{vt}**")

                    with st.chat_message(name=uname, avatar="⚖️"):
                        st.markdown(
                            f"**@{uname}** &nbsp;•&nbsp; {v_badge} &nbsp;•&nbsp; "
                            f"Accuracy: `{b_score:.1%}` (Weight: `{p_weight:.3f}`) &nbsp;•&nbsp; "
                            f"<span style='color:#757575;font-size:0.85em;'>{msg_ts}</span>",
                            unsafe_allow_html=True,
                        )
                        st.markdown(f"> {content_text}")

                        # Display clickable URL badges if present
                        if urls_list is not None and isinstance(urls_list, (list, tuple)) and len(urls_list) > 0:
                            links_md = " ".join([f"[🔗 `{u.split('//')[-1][:35]}...`]({u})" for u in urls_list if u])
                            st.markdown(f"**Evidence & Links:** {links_md}")


# ==============================================================================
# TAB 2: USER INFO & BAYESIAN CALIBRATION
# ==============================================================================
elif tab_selection.startswith("👤 Voter Calibration"):
    st.header("Voter Profiles & Accuracy Leaderboard")
    st.caption(
        f"Formula: **Bayesian Accuracy = ((Prior × N) + Correct Predictions) / (N + Gradeable Predictions)** "
        f"| Settings: **Prior = {prior_score:.2f}**, **N = {trust_number}**"
    )

    with st.spinner("Loading voter calibration data from MotherDuck..."):
        users_raw_df = load_user_profiles()

    if users_raw_df.empty:
        st.warning("No voter records found in vw_dc_user_profiles.")
        st.stop()

    users_df = users_raw_df.copy()

    # --- Compute Bayesian Average Accuracy ---
    # BA = (Prior * N + Correct) / (N + Gradeable)
    users_df["bayesian_accuracy"] = (
        (prior_score * trust_number) + users_df["correct_predictions"]
    ) / (trust_number + users_df["gradeable_predictions"])

    # Format percentages
    users_df["bayesian_acc_pct"] = users_df["bayesian_accuracy"] * 100.0
    users_df["raw_acc_pct"] = users_df["lifetime_accuracy"] * 100.0

    # Sort descending by Bayesian accuracy
    users_df = users_df.sort_values("bayesian_accuracy", ascending=False).reset_index(
        drop=True
    )
    users_df["rank"] = users_df.index + 1

    # Filters
    u_col1, u_col2, u_col3 = st.columns([2, 1, 1])
    with u_col1:
        u_search = st.text_input("🔍 Search Username", "")
    with u_col2:
        calibrated_only = st.checkbox("Calibrated Only (≥ 5 bets)", value=False)
    with u_col3:
        min_gradeable = st.number_input("Min Gradeable Bets", min_value=0, value=0, step=1)

    display_df = users_df.copy()
    if min_accuracy_filter > 0:
        if min_accuracy_type.startswith("Bayesian"):
            display_df = display_df[display_df["bayesian_acc_pct"] >= min_accuracy_filter]
        else:
            display_df = display_df[display_df["raw_acc_pct"] >= min_accuracy_filter]
    if u_search:
        display_df = display_df[
            display_df["author_username"].str.contains(u_search, case=False, na=False)
        ]
    if calibrated_only:
        display_df = display_df[display_df["is_calibrated"] == True]
    if min_gradeable > 0:
        display_df = display_df[display_df["gradeable_predictions"] >= min_gradeable]

    # --- User Leaderboard Table ---
    st.subheader(f"Voter Leaderboard ({len(display_df)} users)")
    st.dataframe(
        display_df[
            [
                "rank",
                "author_username",
                "bayesian_accuracy",
                "lifetime_accuracy",
                "correct_predictions",
                "gradeable_predictions",
                "total_predictions",
                "is_calibrated",
                "last_voted_at",
            ]
        ].style.format(
            {
                "bayesian_accuracy": "{:.2%}",
                "lifetime_accuracy": "{:.2%}",
                "correct_predictions": "{:.0f}",
                "gradeable_predictions": "{:.0f}",
                "total_predictions": "{:.0f}",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )

    st.divider()

    # --- Cohort Accuracy Histogram & Exclusion Cutoff ---
    st.subheader("📊 Voter Bayesian Accuracy Distribution (Cohort Histogram)")
    st.caption(
        "Distribution of Empirical Bayes accuracy across all voters with at least **X gradeable bets**. "
        "The red shaded region highlights voters falling below the **Y% cutoff threshold**."
    )

    h_col1, h_col2 = st.columns(2)
    with h_col1:
        hist_min_bets = st.slider(
            "Minimum Gradeable Bets (X)",
            min_value=0,
            max_value=30,
            value=1,
            step=1,
            help="Filter cohort to only voters with at least X resolved predictions.",
        )
    with h_col2:
        hist_cutoff = st.slider(
            "Exclusion Threshold Cutoff (Y %)",
            min_value=0,
            max_value=100,
            value=int(min_accuracy_filter) if min_accuracy_filter > 0 else 45,
            step=5,
            help="Demarcate and shade all voters with Bayesian accuracy below this threshold.",
        )

    # Filter cohort for histogram
    hist_cohort = users_df[users_df["gradeable_predictions"] >= hist_min_bets].copy()

    if hist_cohort.empty:
        st.info(f"No voters found with at least {hist_min_bets} gradeable bets.")
    else:
        scores = hist_cohort["bayesian_acc_pct"].dropna().values
        total_cohort_users = len(scores)
        excluded_users = int(np.sum(scores < hist_cutoff))
        qualified_users = total_cohort_users - excluded_users
        pct_excluded = (excluded_users / total_cohort_users) * 100.0 if total_cohort_users > 0 else 0.0

        fig_h, ax_h = plt.subplots(figsize=(10, 4.2))

        # 30 Bins from 0 to 100%
        bins = np.linspace(0, 100, 35)

        # Plot histogram bars
        n_vals, bins_out, patches = ax_h.hist(
            scores,
            bins=bins,
            edgecolor="#222222",
            linewidth=0.8,
            zorder=3,
        )

        # Color patches: Red for < cutoff, Green for >= cutoff
        for patch in patches:
            bin_center = patch.get_x() + patch.get_width() / 2.0
            if bin_center < hist_cutoff:
                patch.set_facecolor("#e53935")  # Red
                patch.set_alpha(0.75)
            else:
                patch.set_facecolor("#2e7d32")  # Green
                patch.set_alpha(0.85)

        # Draw Cutoff Line & Shading
        ax_h.axvline(
            hist_cutoff,
            color="#b71c1c",
            linestyle="--",
            linewidth=2.2,
            label=f"Cutoff Threshold: {hist_cutoff}%",
            zorder=5,
        )
        ax_h.axvspan(
            0,
            hist_cutoff,
            color="#ffcdd2",
            alpha=0.35,
            label=f"Excluded Region (< {hist_cutoff}%): {excluded_users} users ({pct_excluded:.1f}%)",
            zorder=1,
        )

        # Prior Baseline Line
        ax_h.axvline(
            prior_score * 100.0,
            color="#616161",
            linestyle=":",
            linewidth=1.5,
            label=f"Prior Baseline ({prior_score*100:.0f}%)",
            zorder=4,
        )

        ax_h.set_xlim(0, 100)
        ax_h.set_xlabel("Empirical Bayes Accuracy (%)", fontsize=10, fontweight="bold")
        ax_h.set_ylabel("Number of Voters", fontsize=10, fontweight="bold")
        ax_h.grid(axis="y", linestyle="--", alpha=0.4, zorder=2)
        ax_h.legend(loc="upper right", frameon=True, fontsize=8.5)

        # Annotation summary badge
        ax_h.text(
            0.02,
            0.95,
            f"Cohort (≥ {hist_min_bets} bets): {total_cohort_users} voters\n"
            f"• Qualified (≥ {hist_cutoff}%): {qualified_users} ({100-pct_excluded:.1f}%)\n"
            f"• Excluded (< {hist_cutoff}%): {excluded_users} ({pct_excluded:.1f}%)\n"
            f"• Mean: {np.mean(scores):.1f}% | Median: {np.median(scores):.1f}%",
            transform=ax_h.transAxes,
            verticalalignment="top",
            fontsize=8.5,
            fontweight="medium",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.9, edgecolor="#bbb"),
            zorder=6,
        )

        st.pyplot(fig_h, bbox_inches="tight")
        plt.close(fig_h)

    st.divider()

    # --- Top Voters Visualization ---
    st.subheader("Top 15 Voters by Bayesian Accuracy")

    top15 = display_df.head(15).copy()
    if not top15.empty:
        fig, ax = plt.subplots(figsize=(10, 5))
        y_pos = range(len(top15))

        # Horizontal Bar Chart comparing Raw vs Bayesian
        bar_width = 0.4
        ax.barh(
            [y - bar_width / 2 for y in y_pos],
            top15["bayesian_acc_pct"],
            height=bar_width,
            color="#2ca02c",
            label="Bayesian Accuracy (%)",
            alpha=0.85,
        )
        ax.barh(
            [y + bar_width / 2 for y in y_pos],
            top15["raw_acc_pct"].fillna(0),
            height=bar_width,
            color="#1f77b4",
            label="Raw Accuracy (%)",
            alpha=0.5,
        )

        ax.set_yticks(y_pos)
        ax.set_yticklabels(
            [
                f"{u} (n={int(g)})"
                for u, g in zip(
                    top15["author_username"], top15["gradeable_predictions"]
                )
            ]
        )
        ax.invert_yaxis()  # Top rank on top
        ax.set_xlabel("Accuracy (%)")
        ax.set_xlim(0, 105)
        ax.axvline(
            prior_score * 100,
            color="grey",
            linestyle="--",
            label=f"Prior ({prior_score*100:.0f}%)",
        )
        ax.grid(axis="x", linestyle="--", alpha=0.5)
        ax.legend(loc="lower right")
        st.pyplot(fig)
        plt.close(fig)
    else:
        st.info("No users to display for current filter.")


# ==============================================================================
# TAB 3: METHODOLOGY & BACKTEST VALIDATION
# ==============================================================================
elif tab_selection.startswith("📖 Methodology"):
    st.header("📖 Methodology, Mathematical Theory & Backtest Validation")
    st.caption("A rigorous mathematical and empirical breakdown of the Polydispute intelligence and arbitrage engine.")

    st.markdown("---")

    # Section 1: Executive Summary & The Arbitrage Thesis
    st.subheader("1. The Core Arbitrage Thesis")
    st.markdown(
        """
        When a Polymarket prediction market enters a dispute, the outcome is determined by **UMA's Optimistic Oracle DVM (Data Verification Mechanism)**.
        During the 24–48 hour dispute window:
        
        1. **Information Asymmetry**: Polymarket orderbook prices often experience heavy lag, irrational panic selling, or inaccurate rumors.
        2. **Leading Signal in Discord**: Active dispute participants, forecasters, and protocol analysts debate evidence in the official UMA Discord `#disputes` channel.
        3. **The Alpha Opportunity**: By extracting, aggregating, and calibration-weighting this crowd consensus in real-time, we construct a synthetic **Crowd-Implied Expected Value** that leads the orderbook price.
        """
    )

    st.markdown("---")

    # Section 2: Mathematical Pipeline
    st.subheader("2. Mathematical Formulation & Pipeline")

    col_m1, col_m2 = st.columns(2)
    with col_m1:
        st.markdown("#### A. Bayesian Forecaster Calibration")
        st.markdown(
            """
            Raw prediction counts suffer from noisy, uncalibrated voters. We compute each voter's **Bayesian Accuracy Score ($S_u$)** using an Empirical Bayes prior:
            
            ```
            S_u = (Prior_P * N + Correct_Predictions) / (N + Gradeable_Predictions)
            ```
            - **Prior Score ($P = 0.50$)**: Baseline accuracy assumed for new voters.
            - **Trust Number ($N = 20$)**: Pseudo-observation sample size required to pull a voter away from the prior.
            """
        )

        st.markdown("#### B. Power Weighting Function")
        st.markdown(
            """
            To heavily reward top-tier forecasters and suppress low-accuracy noise, voter power weights scale exponentially:
            
            ```
            Weight (W_u) = (S_u)^p
            ```
            - **Quadratic ($S^2$, Default)**: Amplifies an 80% accurate voter by **4.0x** over a 40% voter.
            """
        )

    with col_m2:
        st.markdown("#### C. Option 2 Terminal Payoff Vector")
        st.markdown(
            """
            Each discrete vote option has a deterministic payoff under Polymarket's Conditional Tokens Framework (CTF):
            
            | Vote Option | Meaning | Payoff Contribution |
            | :--- | :--- | :--- |
            | **P1** | `NO` | **$0.00** |
            | **P2** | `YES` | **$1.00** |
            | **P3** | `50-50` (Equal Split) | **$0.50** |
            | **P4** | `Too Early` (Status Quo) | **$P_{observed}(t_{vote})$** |
            
            ```
            Implied EV(t) = SUM(W_u * Payoff_u) / SUM(W_u)
            ```
            """
        )

        st.markdown("#### D. Polarized Arbitrage Spread (Δ)")
        st.markdown(
            """
            The directional edge between the Crowd-Implied Settlement EV and the Polymarket Orderbook YES Price:
            
            ```
            If Implied EV > 0.50 (Crowd leans YES):
                Spread Δ = Implied EV - Polymarket Price
                -> Action: BUY YES when Δ > 0

            If Implied EV < 0.50 (Crowd leans NO):
                Spread Δ = Polymarket Price - Implied EV
                -> Action: BUY NO when Δ > 0
            ```
            """
        )

    st.markdown("---")

    # Section 3: Empirical Backtest & Ground Truth Validation
    st.subheader("3. Empirical Backtest & Ground Truth Validation")
    st.caption("Evaluated strictly against **Source A Ground Truth (Polymarket Terminal Settlement Prices)** across all closed historical markets.")

    with st.spinner("Calculating historical backtest metrics..."):
        markets_df = load_disputed_markets()

    if not markets_df.empty:
        # Re-compute classifications for backtest tab
        def classify_gt(row):
            closed = bool(row.get("closed", False))
            p_yes = row.get("yes_price")
            p_no = row.get("no_price")
            status = str(row.get("uma_resolution_status", "")).lower()
            if pd.isna(p_yes):
                return "PENDING"
            p_yes = float(p_yes)
            p_no = float(p_no) if pd.notnull(p_no) else (1.0 - p_yes)
            if p_yes >= 0.99:
                return "P2 (YES)"
            elif p_no >= 0.99 or p_yes <= 0.01:
                return "P1 (NO)"
            elif 0.48 <= p_yes <= 0.52 and (closed or status == "resolved"):
                return "P3 (50-50)"
            elif closed or status == "resolved":
                return "P2 (YES)" if p_yes > 0.60 else ("P1 (NO)" if p_yes < 0.40 else "P3 (50-50)")
            return "OPEN / PENDING"

        def classify_pv(row):
            p1 = row.get("p1_votes", 0) or 0
            p2 = row.get("p2_votes", 0) or 0
            p3 = row.get("p3_votes", 0) or 0
            total_v = p1 + p2 + p3
            if total_v == 0:
                return "NO VOTES"
            if p2 > p1 and p2 > p3:
                return "P2 (YES)"
            elif p1 > p2 and p1 > p3:
                return "P1 (NO)"
            elif p3 > p1 and p3 > p2:
                return "P3 (50-50)"
            return "TIE"

        eval_df = markets_df.copy()
        eval_df["ground_truth"] = [classify_gt(r) for _, r in eval_df.iterrows()]
        eval_df["predominant_vote"] = [classify_pv(r) for _, r in eval_df.iterrows()]

        valid_resolved = eval_df[
            eval_df["ground_truth"].isin(["P2 (YES)", "P1 (NO)", "P3 (50-50)"])
            & (eval_df["total_votes"] > 0)
        ].copy()

        if not valid_resolved.empty:
            valid_resolved["is_correct"] = valid_resolved["ground_truth"] == valid_resolved["predominant_vote"]
            total_resolved_cnt = len(valid_resolved)
            correct_cnt = valid_resolved["is_correct"].sum()
            overall_acc = (correct_cnt / total_resolved_cnt) * 100.0

            yes_df = valid_resolved[valid_resolved["ground_truth"] == "P2 (YES)"]
            yes_acc = (yes_df["is_correct"].sum() / len(yes_df) * 100.0) if len(yes_df) > 0 else 0.0

            no_df = valid_resolved[valid_resolved["ground_truth"] == "P1 (NO)"]
            no_acc = (no_df["is_correct"].sum() / len(no_df) * 100.0) if len(no_df) > 0 else 0.0

            bt_col1, bt_col2, bt_col3, bt_col4 = st.columns(4)
            bt_col1.metric("Historical Resolved Disputes", f"{total_resolved_cnt} Markets")
            bt_col2.metric("Aggregate Win Rate", f"{overall_acc:.1f}%", delta=f"{correct_cnt}/{total_resolved_cnt} Correct Calls")
            bt_col3.metric("YES-Outcome Accuracy", f"{yes_acc:.1f}%", help=f"Win rate on {len(yes_df)} actual YES resolutions")
            bt_col4.metric("NO-Outcome Accuracy", f"{no_acc:.1f}%", help=f"Win rate on {len(no_df)} actual NO resolutions")

            st.markdown("#### Historical Dispute Validation Table")
            st.dataframe(
                valid_resolved[
                    [
                        "market_id",
                        "question",
                        "ground_truth",
                        "predominant_vote",
                        "is_correct",
                        "yes_price",
                        "total_votes",
                        "dispute_start",
                        "closed_time",
                    ]
                ].rename(columns={"is_correct": "Call Correct?"}).style.format(
                    {"yes_price": "${:.3f}", "total_votes": "{:.0f}"}
                ),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No resolved disputed markets with recorded votes currently available.")

    st.markdown("---")

    # Section 4: Structural Limitations & Risk Disclosures
    st.subheader("4. Known Structural Risks & Execution Realities")
    st.markdown(
        """
        1. **UMA Token Stake Overrule**: Discord discussion reflects retail sentiment. On-chain settlement is dictated by UMA ERC-20 token stake. When institutional tokenholders or the UMA Rocks Committee rule contrary to chat, on-chain stake overrides message volume.
        2. **Ambiguity & P3 (50-50) Default**: On ambiguously phrased market questions, DVM voters frequently default to P3 (50-50 equal split) to protect bond collateral.
        3. **Orderbook Depth & Slippage**: Disputed markets often suffer from thin liquidity. Quoted midpoint prices may have 5–10¢ bid-ask spreads.
        """
    )
