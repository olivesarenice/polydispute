import os
import sys
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
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
    """Query unique disputed markets with temporal clustered dispute rounds and thread counts."""
    conn = get_db_conn()
    query = """
    WITH thread_clusters AS (
        SELECT 
            market_id,
            thread_id,
            timestamp,
            CASE 
                WHEN timestamp - LAG(timestamp) OVER (PARTITION BY market_id ORDER BY timestamp ASC) > INTERVAL '36 hours' 
                OR LAG(timestamp) OVER (PARTITION BY market_id ORDER BY timestamp ASC) IS NULL 
                THEN 1 ELSE 0 
            END AS is_new_dispute
        FROM clean_dc_threads
        WHERE market_id IS NOT NULL
    ),
    market_dispute_counts AS (
        SELECT 
            market_id,
            COUNT(DISTINCT thread_id) AS total_threads,
            SUM(is_new_dispute) AS total_dispute_rounds
        FROM thread_clusters
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
        MIN(t.timestamp) AS dispute_start,
        MAX(t.timestamp) AS latest_dispute_start,
        m.closed_time,
        m.uma_end_date,
        COUNT(msg.message_id) AS total_messages,
        COUNT(CASE WHEN msg.vote_type IN ('P1', 'P2', 'P3', 'P4') THEN 1 END) AS total_votes,
        COUNT(CASE WHEN msg.vote_type = 'P1' THEN 1 END) AS p1_votes,
        COUNT(CASE WHEN msg.vote_type = 'P2' THEN 1 END) AS p2_votes,
        COUNT(CASE WHEN msg.vote_type = 'P3' THEN 1 END) AS p3_votes,
        COUNT(CASE WHEN msg.vote_type = 'P4' THEN 1 END) AS p4_votes
    FROM clean_pm_markets m
    JOIN clean_dc_threads t ON m.market_id = t.market_id
    LEFT JOIN market_dispute_counts dc ON m.market_id = dc.market_id
    LEFT JOIN ur_latest ur ON (LOWER(TRIM(m.question)) = LOWER(TRIM(ur.question)) OR ur.ancillary_data LIKE '%' || m.market_id || '%') AND ur.rn = 1
    LEFT JOIN clean_dc_messages msg ON t.thread_id = msg.thread_id AND msg.author_username NOT IN ('UMA Herald', 'UMA Heralds')
    GROUP BY 
        m.market_id, m.question, m.uma_resolution_status, m.closed, 
        m.yes_price, m.no_price, dc.total_dispute_rounds, dc.total_threads,
        ur.ur_answer, m.closed_time, m.uma_end_date
    ORDER BY MIN(t.timestamp) DESC;
    """
    try:
        df = conn.execute(query).df()
        return df
    finally:
        conn.close()


@st.cache_data(ttl=120)
def load_market_dispute_rounds(market_id: str, max_gap_hours: float = 36.0):
    """
    Groups all Discord messages across threads for a market into distinct Dispute Rounds
    using temporal clustering (gap > 36 hours indicates a new dispute round).
    """
    conn = get_db_conn()
    query = f"""
    SELECT 
        t.thread_id,
        t.market_id,
        m.message_id,
        m.author_username,
        m.timestamp,
        m.vote_type
    FROM clean_dc_threads t
    JOIN clean_dc_messages m ON t.thread_id = m.thread_id
    WHERE t.market_id = '{market_id}'
      AND m.author_username NOT IN ('UMA Herald', 'UMA Heralds')
      AND LOWER(m.author_username) NOT LIKE '%herald%'
    ORDER BY m.timestamp ASC;
    """
    try:
        df = conn.execute(query).df()
        if df.empty:
            return pd.DataFrame(), []

        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.sort_values("timestamp").reset_index(drop=True)

        # Calculate time gap between consecutive dispute messages
        df["gap_hours"] = df["timestamp"].diff().dt.total_seconds() / 3600.0
        df["is_new_round"] = (df["gap_hours"] > max_gap_hours) | df["gap_hours"].isna()
        df["round_num"] = df["is_new_round"].cumsum()

        rounds_summary = []
        for r_num, group in df.groupby("round_num"):
            r_start = group["timestamp"].min()
            r_end = group["timestamp"].max()
            threads = sorted(list(group["thread_id"].unique()))
            total_votes = len(group[group["vote_type"].isin(["P1", "P2", "P3", "P4"])])
            unique_voters = group["author_username"].nunique()

            rounds_summary.append({
                "round_num": int(r_num),
                "round_start": r_start,
                "round_end": r_end,
                "thread_ids": threads,
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

    # Build User Bayesian Score lookup map
    user_score_map = {}
    if not users_raw_df.empty:
        for _, u_row in users_raw_df.iterrows():
            uname = u_row["author_username"]
            g_preds = u_row["gradeable_predictions"] or 0
            c_preds = u_row["correct_predictions"] or 0.0
            # S = (P * N + C) / (N + G)
            b_score = ((prior_score * trust_number) + c_preds) / (trust_number + g_preds)
            user_score_map[uname] = b_score

    def get_user_power(username: str) -> tuple[float, float]:
        """Returns (bayesian_score, power_weight)."""
        score = user_score_map.get(username, prior_score)
        power = score ** power_exponent
        return score, power

    # --- Compute Market-Level Live Spread & Ground Truth ---
    def classify_ground_truth(row):
        closed = bool(row.get("closed", False))
        p_yes = row.get("yes_price")
        p_no = row.get("no_price")
        status = str(row.get("uma_resolution_status", "")).lower()

        if pd.isna(p_yes):
            return "PENDING / UNKNOWN"

        p_yes = float(p_yes)
        p_no = float(p_no) if pd.notnull(p_no) else (1.0 - p_yes)

        # Source A Ground Truth Rules (Polymarket Terminal Settlement)
        if p_yes >= 0.99:
            return "P2 (YES)"
        elif p_no >= 0.99 or p_yes <= 0.01:
            return "P1 (NO)"
        elif 0.48 <= p_yes <= 0.52 and (closed or status == "resolved"):
            return "P3 (50-50)"
        elif closed or status == "resolved":
            if p_yes > 0.60:
                return "P2 (YES)"
            elif p_yes < 0.40:
                return "P1 (NO)"
            else:
                return "P3 (50-50)"
        else:
            return "OPEN / PENDING"

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
    col_f1, col_f2, col_f3, col_f4 = st.columns([2, 1, 1, 1])
    with col_f1:
        search_query = st.text_input("🔍 Search Question or Market ID", "")
    with col_f2:
        status_filter = st.selectbox(
            "Resolution Status",
            ["All"] + sorted(list(markets_df["uma_resolution_status"].dropna().unique())),
        )
    with col_f3:
        only_arb = st.checkbox("🟢 Arbitrage Only (Spread > 0)", value=False)
    with col_f4:
        min_votes_filter = st.number_input("Min Votes", min_value=0, value=0, step=1)

    filtered_df = markets_df.copy()
    if search_query:
        filtered_df = filtered_df[
            filtered_df["question"].str.contains(search_query, case=False, na=False)
            | filtered_df["market_id"].str.contains(search_query, case=False, na=False)
        ]
    if status_filter != "All":
        filtered_df = filtered_df[filtered_df["uma_resolution_status"] == status_filter]
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
            "ground_truth",
            "uma_resolution_status",
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
    m_col2.metric("Resolution Status", str(selected_row["uma_resolution_status"]).upper())
    m_col3.metric("UR Committee Submit", str(selected_row.get("ur_committee_signal") or "N/A").upper())
    m_col4.metric(
        "Current YES / NO Price",
        f"${selected_row['yes_price']:.3f} / ${selected_row['no_price']:.3f}"
        if pd.notnull(selected_row["yes_price"])
        else "N/A",
    )
    m_col5.metric("Dispute Rounds", f"{total_rounds_count} Round(s)")

    # Dispute Round Selector (if market was disputed multiple times)
    if total_rounds_count > 1:
        st.info(f"🔔 **Multi-Round Dispute Detected:** Temporal clustering identified **{total_rounds_count} separate dispute rounds** (>36h gap).")
        round_choices = ["All Rounds (Combined Timeline)"] + [
            f"Round {r['round_num']} ({r['round_start'].strftime('%Y-%m-%d %H:%M')} – {r['round_end'].strftime('%Y-%m-%d %H:%M')} | {r['total_votes']} votes | {len(r['thread_ids'])} thread(s))"
            for r in rounds_summary
        ]
        selected_round_choice = st.radio(
            "Select Dispute Round to Zoom In:",
            round_choices,
            horizontal=True,
        )

        if selected_round_choice.startswith("All Rounds"):
            votes_df = all_msgs_df[all_msgs_df["vote_type"].isin(["P1", "P2", "P3", "P4"])].copy()
            view_label = f"All {total_rounds_count} Rounds Combined"
        else:
            chosen_idx = round_choices.index(selected_round_choice) - 1
            chosen_r = rounds_summary[chosen_idx]
            votes_df = all_msgs_df[
                (all_msgs_df["round_num"] == chosen_r["round_num"])
                & all_msgs_df["vote_type"].isin(["P1", "P2", "P3", "P4"])
            ].copy()
            view_label = f"Dispute Round {chosen_r['round_num']}"
    else:
        votes_df = all_msgs_df[all_msgs_df["vote_type"].isin(["P1", "P2", "P3", "P4"])].copy() if not all_msgs_df.empty else pd.DataFrame()
        view_label = "Dispute Round 1"

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

                shade_color = round_palette[idx % len(round_palette)]
                line_color = line_palette[idx % len(line_palette)]

                ax_top.axvspan(
                    t_r_start,
                    t_r_end,
                    color=shade_color,
                    alpha=0.18,
                    label=f"Dispute Round {r['round_num']} ({t_r_start.strftime('%m/%d %H:%M')} – {t_r_end.strftime('%m/%d %H:%M')})",
                )
                ax_top.axvline(
                    t_r_start,
                    color=line_color,
                    linestyle="--",
                    linewidth=1.8,
                    alpha=0.85,
                    label=f"Round {r['round_num']} Start",
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

    # 2. Bottom Chart: Dispute Window Overlay (Solid Weighted + Dashed Raw + YES Price)
    power_label = "S²" if power_exponent == 2.0 else f"S^{power_exponent:g}"
    st.markdown(f"#### 🗳️ 2. Dispute Window ({view_label}): Weighted (Solid — {power_label}) vs. Raw (Dashed - -) Consensus & YES Price Overlay")

    if not has_votes:
        st.info("No DVM votes recorded in this thread yet.")
    else:
        fig_bot, ax_left = plt.subplots(figsize=(12, 5.2))
        ax_right = ax_left.twinx()  # Secondary y-axis for YES Price

        # A. Plot Left Axis: Consensus Shares (%)
        for vt in vote_types:
            if consensus_ts_df[f"{vt}_raw_cnt"].iloc[-1] > 0:
                final_w_pct = consensus_ts_df[f"{vt}_weighted_pct"].iloc[-1]
                final_r_pct = consensus_ts_df[f"{vt}_raw_pct"].iloc[-1]

                # Solid line for Bayesian Weighted Share
                ax_left.plot(
                    consensus_ts_df["timestamp"],
                    consensus_ts_df[f"{vt}_weighted_pct"],
                    color=colors[vt],
                    linestyle="-",
                    linewidth=2.4,
                    label=f"{vote_labels[vt]} (Weighted: {final_w_pct:.1f}%)",
                )
                # Dashed line for Raw Unweighted Share
                ax_left.plot(
                    consensus_ts_df["timestamp"],
                    consensus_ts_df[f"{vt}_raw_pct"],
                    color=colors[vt],
                    linestyle="--",
                    linewidth=1.5,
                    alpha=0.65,
                    label=f"{vote_labels[vt]} (Raw: {final_r_pct:.1f}%)",
                )

        ax_left.set_ylim(-5, 105)
        ax_left.set_ylabel("Vote / Consensus Share (%)", color="#2c3e50", fontsize=11, fontweight="bold")
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

        st.caption(
            "Direct comparison on a unified $0.00–$1.00 scale: "
            "**Calibration-Weighted EV** (Solid Green) vs. **Raw EV** (Dashed Orange) vs. **Orderbook YES Price** (Solid Black). "
            "P4 (Too Early) votes contribute the point-in-time market YES price observed immediately prior to each vote."
        )

        final_w_ev = consensus_ts_df["weighted_implied_ev"].iloc[-1]
        final_r_ev = consensus_ts_df["raw_implied_ev"].iloc[-1]

        fig_ev, ax_ev = plt.subplots(figsize=(12, 4.5))

        # Line 1: Calibration-Weighted Crowd Implied EV
        ax_ev.plot(
            consensus_ts_df["timestamp"],
            consensus_ts_df["weighted_implied_ev"],
            color="#2e7d32",
            linestyle="-",
            linewidth=2.5,
            label=f"Calibration-Weighted Implied EV ({power_label}): ${final_w_ev:.3f}",
        )

        # Line 2: Raw Unweighted Crowd Implied EV
        ax_ev.plot(
            consensus_ts_df["timestamp"],
            consensus_ts_df["raw_implied_ev"],
            color="#ff9800",
            linestyle="--",
            linewidth=1.8,
            alpha=0.85,
            label=f"Raw Unweighted Implied EV: ${final_r_ev:.3f}",
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

        # D. Detailed Vote Stream Expander
        with st.expander("Show Detailed Vote Stream with Bayesian Weights", expanded=False):
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
