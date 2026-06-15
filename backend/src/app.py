import os
import sqlite3
from pathlib import Path

import sentry_sdk
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from loguru import logger

from backend.src.schemas import (
    DisputeSignal,
    HealthResponse,
    MarketDetail,
    PipelineStatus,
    SignalsResponse,
    StancesResponse,
    DiscordStance,
)

# ---------------------------------------------------------------------------
# Sentry (optional — only initializes when DSN is provided)
# ---------------------------------------------------------------------------
SENTRY_DSN = os.getenv("SENTRY_DSN")
if SENTRY_DSN:
    sentry_sdk.init(dsn=SENTRY_DSN, traces_sample_rate=0.2)
    logger.info("Sentry initialized")

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="Polydispute API", version="3.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Database helper
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = PROJECT_ROOT / "pipeline" / "data" / "polydispute.db"


def _get_conn() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise HTTPException(
            status_code=503,
            detail=f"Database not found at {DB_PATH}. Run the pipeline first.",
        )
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/api/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    return HealthResponse(status="ok", version="v3.1-selective")


@app.get("/api/signals/arb", response_model=SignalsResponse)
def get_arb_signals() -> SignalsResponse:
    """
    Returns dispute signals from disputes_view with computed tau and arb spread.
    tau_yes = P1 / (P1 + P2) — community-implied YES probability.
    arb_spread = |yes_price - tau_yes|.
    """
    conn = _get_conn()
    try:
        rows = conn.execute("SELECT * FROM disputes_view").fetchall()
    except sqlite3.OperationalError as e:
        logger.warning(f"disputes_view query failed: {e}")
        return SignalsResponse(signals=[], count=0)
    finally:
        conn.close()

    signals: list[DisputeSignal] = []
    for row in rows:
        d = dict(row)
        total = (d.get("p1_votes") or 0) + (d.get("p2_votes") or 0) + \
                (d.get("p3_votes") or 0) + (d.get("p4_votes") or 0)

        # Compute tau: P1 = YES outcome, P2 = NO outcome
        p1 = d.get("p1_votes") or 0
        p2 = d.get("p2_votes") or 0
        tau_yes = p1 / (p1 + p2) if (p1 + p2) > 0 else None

        yes_price = d.get("yes_price")
        arb_spread = abs(yes_price - tau_yes) if (yes_price is not None and tau_yes is not None) else None

        # Determine dominant vote
        votes = {"P1": p1, "P2": p2, "P3": d.get("p3_votes") or 0, "P4": d.get("p4_votes") or 0}
        dominant = max(votes, key=votes.get) if total > 0 else None

        signals.append(DisputeSignal(
            thread_id=d["thread_id"],
            condition_id=d.get("condition_id"),
            question=d.get("question"),
            slug=d.get("slug"),
            uma_resolution_status=d.get("uma_resolution_status"),
            uma_bond=d.get("uma_bond"),
            uma_reward=d.get("uma_reward"),
            neg_risk=bool(d.get("neg_risk")) if d.get("neg_risk") is not None else None,
            yes_price=yes_price,
            no_price=d.get("no_price"),
            p1_votes=p1,
            p2_votes=p2,
            p3_votes=d.get("p3_votes") or 0,
            p4_votes=d.get("p4_votes") or 0,
            total_votes=total,
            dominant_vote=dominant,
            tau_yes=round(tau_yes, 4) if tau_yes is not None else None,
            arb_spread=round(arb_spread, 4) if arb_spread is not None else None,
        ))

    # Sort by arb_spread descending (biggest edge first), nulls last
    signals.sort(key=lambda s: s.arb_spread if s.arb_spread is not None else -1, reverse=True)

    return SignalsResponse(signals=signals, count=len(signals))


@app.get("/api/signals/discord", response_model=StancesResponse)
def get_discord_stances(market_id: str) -> StancesResponse:
    """Vote breakdown per Discord thread for a given market_id."""
    conn = _get_conn()
    try:
        rows = conn.execute("""
            SELECT 
                t.thread_id,
                t.market_id,
                COUNT(CASE WHEN v.vote_type = 'P1' THEN 1 END) AS p1_votes,
                COUNT(CASE WHEN v.vote_type = 'P2' THEN 1 END) AS p2_votes,
                COUNT(CASE WHEN v.vote_type = 'P3' THEN 1 END) AS p3_votes,
                COUNT(CASE WHEN v.vote_type = 'P4' THEN 1 END) AS p4_votes
            FROM clean_dc_threads t
            LEFT JOIN clean_dc_messages v ON t.thread_id = v.thread_id
            WHERE t.market_id = ?
            GROUP BY t.thread_id
        """, (market_id,)).fetchall()
    except sqlite3.OperationalError as e:
        logger.warning(f"Discord stances query failed: {e}")
        return StancesResponse(market_id=market_id, stances=[])
    finally:
        conn.close()

    stances = [DiscordStance(**dict(row)) for row in rows]
    return StancesResponse(market_id=market_id, stances=stances)


@app.get("/api/markets/{condition_id}", response_model=MarketDetail)
def get_market_detail(condition_id: str) -> MarketDetail:
    """Detailed market info including on-chain resolution rules."""
    conn = _get_conn()
    try:
        row = conn.execute("""
            SELECT 
                m.condition_id, m.market_id, m.question, m.slug,
                m.yes_price, m.no_price, m.uma_resolution_status,
                m.uma_bond, m.uma_reward, m.neg_risk,
                p.ancillary_data_decoded
            FROM clean_pm_markets m
            LEFT JOIN clean_polygon_ancillary p ON m.uma_question_id = p.uma_question_id
            WHERE m.condition_id = ?
        """, (condition_id,)).fetchone()
    except sqlite3.OperationalError as e:
        raise HTTPException(status_code=503, detail=str(e))
    finally:
        conn.close()

    if not row:
        raise HTTPException(status_code=404, detail=f"Market {condition_id} not found")

    return MarketDetail(**dict(row))


@app.get("/api/pipeline/status", response_model=list[PipelineStatus])
def get_pipeline_status() -> list[PipelineStatus]:
    """Last 10 pipeline runs."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT run_id, mode, start_time, end_time, status FROM pipeline_runs ORDER BY start_time DESC LIMIT 10"
        ).fetchall()
    except sqlite3.OperationalError as e:
        logger.warning(f"Pipeline status query failed: {e}")
        return []
    finally:
        conn.close()

    return [PipelineStatus(**dict(row)) for row in rows]


# ---------------------------------------------------------------------------
# Static frontend — MUST be mounted last so API routes take precedence
# ---------------------------------------------------------------------------
FRONTEND_DIR = PROJECT_ROOT / "frontend" / "dist"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
else:
    @app.get("/")
    def index() -> dict[str, str]:
        return {"message": "Frontend not built. Run 'npm run build' in frontend/."}


if __name__ == "__main__":
    logger.info("Starting FastAPI server on port 8000")
    uvicorn.run("backend.src.app:app", host="0.0.0.0", port=8000, reload=True)
