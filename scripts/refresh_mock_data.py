import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Setup paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
MOCK_FILE = FRONTEND_DIR / "src" / "mock" / "mockData.js"
PIPELINE_SRC = PROJECT_ROOT / "pipeline" / "src"

if str(PIPELINE_SRC) not in sys.path:
    sys.path.insert(0, str(PIPELINE_SRC))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.src.app import classify_market_status, parse_dt

try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
    load_dotenv(PIPELINE_SRC / ".env")
except Exception:
    pass

if not os.getenv("MOTHERDUCK_TOKEN"):
    try:
        import subprocess
        token = subprocess.check_output(
            ["doppler", "secrets", "get", "MOTHERDUCK_TOKEN", "--plain"], 
            cwd=str(PROJECT_ROOT / "pipeline"),
            text=True
        ).strip()
        if token:
            os.environ["MOTHERDUCK_TOKEN"] = token
    except Exception:
        pass


def parse_iso(ts_str):
    if not ts_str:
        return None
    try:
        clean = str(ts_str).replace("Z", "+00:00")
        return datetime.fromisoformat(clean)
    except Exception:
        return None


def fetch_fresh_markets_from_motherduck(cutoff_dt: datetime):
    """Query fresh markets from MotherDuck data warehouse for the past 60 days."""
    from db_utils import get_db_conn
    conn = get_db_conn()
    print("Connected to MotherDuck! Extracting markets...")

    cutoff_str = cutoff_dt.strftime("%Y-%m-%d")
    
    # Check tables available
    tables = [r[0] for r in conn.execute("SHOW TABLES").fetchall()]
    print(f"Available tables: {tables}")

    query = f"""
    WITH market_thread_stats AS (
        SELECT 
            market_id,
            COUNT(DISTINCT thread_id) AS total_threads,
            COUNT(DISTINCT thread_id) AS total_dispute_rounds
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
    )
    SELECT 
        m.market_id,
        m.question,
        m.slug,
        raw.description,
        m.uma_resolution_status,
        m.closed,
        m.yes_price,
        m.no_price,
        COALESCE(dc.total_dispute_rounds, 1) AS total_rounds,
        COALESCE(dc.total_threads, 1) AS total_threads,
        MAX(t.timestamp) AS dispute_start,
        raw.closed_time,
        raw.uma_end_date,
        COALESCE(va.total_votes, 0) AS total_votes,
        COALESCE(va.p1_votes, 0) AS p1_votes,
        COALESCE(va.p2_votes, 0) AS p2_votes,
        COALESCE(va.p3_votes, 0) AS p3_votes,
        COALESCE(va.p4_votes, 0) AS p4_votes
    FROM clean_pm_markets m
    JOIN clean_dc_threads t ON m.market_id = t.market_id
    LEFT JOIN raw_pm_markets raw ON m.market_id = raw.id
    LEFT JOIN market_thread_stats dc ON m.market_id = dc.market_id
    LEFT JOIN market_vote_aggregations va ON m.market_id = va.market_id
    WHERE (
        m.closed = false 
        OR raw.closed_time >= '{cutoff_str}' 
        OR raw.uma_end_date >= '{cutoff_str}' 
        OR t.timestamp >= '{cutoff_str}'
    )
    GROUP BY 
        m.market_id, m.question, m.slug, raw.description, m.uma_resolution_status, m.closed, 
        m.yes_price, m.no_price, dc.total_dispute_rounds, dc.total_threads,
        va.total_votes, va.p1_votes, va.p2_votes, va.p3_votes, va.p4_votes,
        raw.closed_time, raw.uma_end_date
    ORDER BY MAX(t.timestamp) DESC;
    """

    df = conn.execute(query).df()
    conn.close()
    print(f"Extracted {len(df)} markets from MotherDuck for window >= {cutoff_str}")

    screener_list = []
    for _, row in df.iterrows():
        total_v = int(row.get("total_votes", 0))
        p1 = int(row.get("p1_votes", 0))
        p2 = int(row.get("p2_votes", 0))
        p3 = int(row.get("p3_votes", 0))
        p4 = int(row.get("p4_votes", 0))

        # Determine predominant vote
        predominant = "N/A"
        if total_v > 0:
            votes_map = {"NO": p1, "YES": p2, "50-50": p3, "EARLY": p4}
            top_label, top_count = max(votes_map.items(), key=lambda x: x[1])
            pct = int(round((top_count / total_v) * 100))
            predominant = f"{top_label} ({pct}%)"

        is_closed = bool(row.get("closed", False))
        uma_status = str(row.get("uma_resolution_status", "")).lower()
        yes_p = float(row.get("yes_price", 0.5)) if row.get("yes_price") is not None else 0.5
        no_p = float(row.get("no_price", 0.5)) if row.get("no_price") is not None else 0.5

        disp_start_val = row.get("dispute_start")
        disp_start_dt = parse_dt(disp_start_val)

        status_code, status_label, is_live = classify_market_status(
            is_closed=is_closed,
            uma_status=uma_status,
            yes_p=yes_p,
            no_p=no_p,
            dispute_start_dt=disp_start_dt,
            p1_votes=p1,
            p2_votes=p2,
            p3_votes=p3,
            p4_votes=p4,
        )

        screener_list.append({
            "market_id": str(row["market_id"]),
            "question": str(row.get("question", "")),
            "slug": str(row.get("slug", "")),
            "description": str(row.get("description", "")),
            "market_status_code": status_code,
            "market_status_label": status_label,
            "is_live_dispute": is_live,
            "latest_dispute_started": str(row["dispute_start"]) if row.get("dispute_start") else None,
            "market_closed_time": str(row["closed_time"]) if row.get("closed_time") else None,
            "market_specified_end_time": str(row["uma_end_date"]) if row.get("uma_end_date") else None,
            "yes_price": yes_p,
            "no_price": no_p,
            "total_voters": total_v,
            "predominant_vote": predominant,
            "p1_votes": p1,
            "p2_votes": p2,
            "p3_votes": p3,
            "p4_votes": p4,
            "total_rounds": int(row.get("total_rounds", 1)),
            "ur_committee_signal": "N/A"
        })

    return screener_list


def main():
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=60)
    print(f"=== REFRESHING MOCK DATA FOR PAST 60 DAYS ({cutoff.strftime('%Y-%m-%d')} to {now.strftime('%Y-%m-%d')}) ===")

    # Load existing market_details to preserve detailed charts
    existing_details = {}
    if os.path.exists(MOCK_FILE):
        with open(MOCK_FILE, "r", encoding="utf-8") as f:
            content = f.read()
        details_match = re.search(r"export const mockMarketDetails = (\{.*?\});\s*(?:export const|$)", content, re.DOTALL)
        if details_match:
            try:
                existing_details = json.loads(details_match.group(1))
            except Exception as e:
                print(f"Notice: Could not parse existing details: {e}")

    try:
        screener_markets = fetch_fresh_markets_from_motherduck(cutoff)
        print(f"Successfully extracted {len(screener_markets)} live markets from MotherDuck!")
    except Exception as e:
        print(f"MotherDuck live pull error: {e}")
        print("Falling back to local mock filter...")
        sys.exit(1)

    settings = {
        "minExperienceVotes": 10,
        "minCompetencyPct": 50,
        "trustNumber": 20,
        "priorScore": 0.50,
        "weightingMethod": "S^2"
    }

    # Write out updated mock file
    js_content = (
        "// Real extracted dataset from MotherDuck data warehouse for Polydispute UI\n"
        f"// Refreshed directly from MotherDuck: {now.isoformat()} (60-day window)\n\n"
        f"export const mockScreenerMarkets = {json.dumps(screener_markets, indent=2)};\n\n"
        f"export const mockMarketDetails = {json.dumps(existing_details, indent=2)};\n\n"
        f"export const mockDefaultSettings = {json.dumps(settings, indent=2)};\n"
    )

    with open(MOCK_FILE, "w", encoding="utf-8") as f:
        f.write(js_content)

    print(f"✅ Successfully refreshed {MOCK_FILE} with {len(screener_markets)} markets directly from MotherDuck!")


if __name__ == "__main__":
    main()
