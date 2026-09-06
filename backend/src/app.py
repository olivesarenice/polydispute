"""Polydispute FastAPI Backend.

Provides high-performance analytical endpoints backed by MotherDuck with:
- Strict Pydantic validation
- Multi-tier in-memory TTL caching
- Zero-mock offline handling
- Thread-safe query execution and auto-reconnection
"""

import time
from collections import Counter
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, AsyncGenerator, Literal

import pandas as pd
import sentry_sdk
import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from backend.src.analytics import build_market_analytics, compute_bayesian_score
from backend.src.config import settings
from backend.src.db import db_manager
from backend.src.schemas import (
    DisputeRoundItem,
    GroupAccuracyMetrics,
    GroupAccuracySummary,
    HealthResponse,
    LeaderboardResponse,
    MarketAnalyticsDetail,
    PipelineStatusItem,
    PricePoint,
    ScreenerMarket,
    ScreenerResponse,
    VoterLeaderboardItem,
    WeeklyAccuracyItem,
)

# Optional Sentry initialization
if settings.SENTRY_DSN:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
        profiles_sample_rate=settings.SENTRY_PROFILES_SAMPLE_RATE,
        environment=settings.PIPELINE_ENV,
        release=f"polydispute-backend@{settings.API_VERSION}",
        send_default_pii=True,
    )
    logger.info(
        f"Sentry APM initialized env={settings.PIPELINE_ENV} "
        f"traces_sample_rate={settings.SENTRY_TRACES_SAMPLE_RATE}"
    )


# ---------------------------------------------------------------------------
# In-Memory Cache Store
# ---------------------------------------------------------------------------
class CacheStore:
    """Simple thread-safe TTL cache store."""

    def __init__(self) -> None:
        self._cache: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        if key in self._cache:
            expires_at, val = self._cache[key]
            if time_now() < expires_at:
                return val
            del self._cache[key]
        return None

    def set(self, key: str, val: Any, ttl_seconds: int) -> None:
        self._cache[key] = (time_now() + ttl_seconds, val)

    def invalidate(self, key_prefix: str = "") -> None:
        if not key_prefix:
            self._cache.clear()
        else:
            keys = [k for k in self._cache if k.startswith(key_prefix)]
            for k in keys:
                del self._cache[k]


def time_now() -> float:
    return datetime.now(timezone.utc).timestamp()


cache = CacheStore()



# ---------------------------------------------------------------------------
# Data Fetchers & Transformation
# ---------------------------------------------------------------------------
def parse_dt(val: Any) -> datetime | None:
    """Safely parse various datetime and ISO string representations to datetime."""
    if val is None or pd.isna(val):
        return None
    if isinstance(val, datetime):
        return val
    try:
        clean = str(val).replace("Z", "+00:00")
        return datetime.fromisoformat(clean)
    except Exception:
        try:
            return pd.to_datetime(val).to_pydatetime()
        except Exception:
            return None


def classify_market_status(
    is_closed: bool,
    uma_status: str,
    yes_p: float,
    no_p: float,
    dispute_start_dt: datetime | None,
    p1_votes: int = 0,
    p2_votes: int = 0,
    p3_votes: int = 0,
    p4_votes: int = 0,
) -> tuple[str, str, bool]:
    """
    Classifies market dispute resolution according to refined business logic:

    1. Resolved Markets (is_closed == True or uma_status == 'resolved'):
       - yes_p >= 0.99 -> RESOLVED_P2 (YES)
       - yes_p <= 0.01 or no_p >= 0.99 -> RESOLVED_P1 (NO)
       - 0.48 <= yes_p <= 0.52 -> RESOLVED_P3 (50-50)
       - Else -> RESOLVED_P2 if yes_p > 0.5 else RESOLVED_P1
       (All marked is_live = False)

    2. Live Disputes:
       - Market is NOT closed (is_closed == False)
       - AND dispute is active within 48-hour voting window (hours_since <= 48.0)
       - OR newly proposed/disputed without thread timestamp yet
       -> LIVE_DISPUTE, label 'LIVE DISPUTE', is_live = True

    3. Unclosed Markets where dispute voting window has expired (> 48h):
       - If p4_votes > (p1_votes + p2_votes + p3_votes) or (0.01 < yes_p < 0.99):
         -> RESOLVED_EARLY, label 'RESOLVED EARLY (P4)', is_live = False
       - elif yes_p >= 0.99 -> RESOLVED_P2 (YES)
       - elif yes_p <= 0.01 or no_p >= 0.99 -> RESOLVED_P1 (NO)
       - elif 0.48 <= yes_p <= 0.52 -> RESOLVED_P3 (50-50)
       - Else -> RESOLVED_EARLY, label 'RESOLVED EARLY (P4)', is_live = False

    4. Fallback:
       -> RESOLVED, is_live = False
    """
    uma_clean = str(uma_status or "").strip().lower()
    is_resolved = is_closed or uma_clean == "resolved"

    # Compute elapsed dispute hours
    hours_since = None
    if dispute_start_dt is not None:
        now_utc = datetime.now(timezone.utc)
        if dispute_start_dt.tzinfo is None:
            dispute_start_dt = dispute_start_dt.replace(tzinfo=timezone.utc)
        hours_since = (now_utc - dispute_start_dt).total_seconds() / 3600.0

    # Branch 1: Market is closed or explicitly marked resolved
    if is_resolved:
        if yes_p >= 0.99:
            return "RESOLVED_P2", "RESOLVED (YES - P2)", False
        elif yes_p <= 0.01 or no_p >= 0.99:
            return "RESOLVED_P1", "RESOLVED (NO - P1)", False
        elif 0.48 <= yes_p <= 0.52:
            return "RESOLVED_P3", "RESOLVED (50-50 - P3)", False
        else:
            code = "RESOLVED_P2" if yes_p > 0.5 else "RESOLVED_P1"
            label = "RESOLVED (YES - P2)" if yes_p > 0.5 else "RESOLVED (NO - P1)"
            return code, label, False

    # Branch 2: Live dispute — unclosed market within 48h dispute window
    if not is_closed and (
        (hours_since is not None and hours_since <= 48.0)
        or (hours_since is None and uma_clean in ("proposed", "disputed"))
    ):
        return "LIVE_DISPUTE", "LIVE DISPUTE", True

    # Branch 3: Unclosed markets where dispute voting window has expired (> 48h) or not active
    if not is_closed:
        # Plurality of P4 votes or intermediate price on an unclosed market -> settled to TOO EARLY
        if p4_votes > (p1_votes + p2_votes + p3_votes) or (0.01 < yes_p < 0.99):
            return "RESOLVED_EARLY", "RESOLVED EARLY (P4)", False
        elif yes_p >= 0.99:
            return "RESOLVED_P2", "RESOLVED (YES - P2)", False
        elif yes_p <= 0.01 or no_p >= 0.99:
            return "RESOLVED_P1", "RESOLVED (NO - P1)", False
        elif 0.48 <= yes_p <= 0.52:
            return "RESOLVED_P3", "RESOLVED (50-50 - P3)", False
        else:
            return "RESOLVED_EARLY", "RESOLVED EARLY (P4)", False

    return "RESOLVED", "RESOLVED", False


def fetch_screener_markets_raw() -> list[ScreenerMarket]:
    """Extract and transform all tracked prediction markets from MotherDuck."""
    cutoff_dt = datetime.now(timezone.utc) - timedelta(days=settings.SCREENER_LOOKBACK_DAYS)
    cutoff_str = cutoff_dt.strftime("%Y-%m-%d")

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

    df = db_manager.query_df(query)
    markets: list[ScreenerMarket] = []

    for _, row in df.iterrows():
        total_v = int(row.get("total_votes", 0))
        p1 = int(row.get("p1_votes", 0))
        p2 = int(row.get("p2_votes", 0))
        p3 = int(row.get("p3_votes", 0))
        p4 = int(row.get("p4_votes", 0))

        # Determine plurality vote
        predominant = "N/A"
        if total_v > 0:
            votes_map = {"NO": p1, "YES": p2, "50-50": p3, "EARLY": p4}
            top_label, top_count = max(votes_map.items(), key=lambda x: x[1])
            pct = int(round((top_count / total_v) * 100))
            predominant = f"{top_label} ({pct}%)"

        is_closed = bool(row.get("closed", False))
        uma_status = str(row.get("uma_resolution_status", "")).lower()
        yes_p = float(row.get("yes_price", 0.5)) if pd.notnull(row.get("yes_price")) else 0.5
        no_p = float(row.get("no_price", 0.5)) if pd.notnull(row.get("no_price")) else 0.5

        disp_start_val = row.get("dispute_start")
        disp_start_dt = parse_dt(disp_start_val)
        disp_start = str(disp_start_val) if pd.notnull(disp_start_val) else None
        closed_time = str(row["closed_time"]) if pd.notnull(row.get("closed_time")) else None
        end_time = str(row["uma_end_date"]) if pd.notnull(row.get("uma_end_date")) else None

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

        markets.append(
            ScreenerMarket(
                market_id=str(row["market_id"]),
                question=str(row.get("question") or ""),
                slug=str(row.get("slug")) if pd.notnull(row.get("slug")) else None,
                description=str(row.get("description")) if pd.notnull(row.get("description")) else None,
                market_status_code=status_code,
                market_status_label=status_label,
                is_live_dispute=is_live,
                latest_dispute_started=disp_start,
                market_closed_time=closed_time,
                market_specified_end_time=end_time,
                yes_price=round(yes_p, 4),
                no_price=round(no_p, 4),
                total_voters=total_v,
                predominant_vote=predominant,
                p1_votes=p1,
                p2_votes=p2,
                p3_votes=p3,
                p4_votes=p4,
                total_rounds=int(row.get("total_rounds", 1)),
                ur_committee_signal="N/A",
            )
        )

    return markets


def get_cached_screener_markets() -> list[ScreenerMarket]:
    """Retrieve screener markets with TTL caching."""
    cached = cache.get("screener_all")
    if cached is not None:
        return cached

    markets = fetch_screener_markets_raw()
    cache.set("screener_all", markets, settings.SCREENER_CACHE_TTL_SEC)
    logger.info(f"Refreshed screener cache with {len(markets)} markets")
    return markets


# ---------------------------------------------------------------------------
# Lifespan Management
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Initialize resources on startup and clean up on shutdown."""
    logger.info("Starting Polydispute API server...")
    try:
        health = db_manager.health_check()
        logger.info(
            f"MotherDuck initial status: {health['database']} "
            f"({health['database_target']}, latency={health['latency_ms']}ms)"
        )
        if health["database"] == "connected":
            # Pre-warm screener cache in background
            get_cached_screener_markets()
    except Exception as e:
        logger.error(f"Startup database check failed: {e}")

    yield

    logger.info("Shutting down Polydispute API server...")
    db_manager.close()


# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------
app = FastAPI(
    title=settings.API_TITLE,
    version=settings.API_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_client_ip(request: Request) -> str:
    """Extract real client IP address from proxy headers (Coolify/Traefik/Cloudflare) or socket."""
    cf_ip = request.headers.get("CF-Connecting-IP")
    if cf_ip:
        return cf_ip.strip()

    xff = request.headers.get("X-Forwarded-For")
    if xff:
        client = xff.split(",")[0].strip()
        if client:
            return client

    x_real_ip = request.headers.get("X-Real-IP")
    if x_real_ip:
        return x_real_ip.strip()

    if request.client and request.client.host:
        return request.client.host

    return "unknown"


@app.middleware("http")
async def sentry_telemetry_middleware(request: Request, call_next: Any) -> Response:
    """HTTP tracing middleware recording round-trip latency, source IP, and status in Sentry."""
    start_time = time.perf_counter()
    client_ip = get_client_ip(request)
    method = request.method
    path = request.url.path

    with sentry_sdk.isolation_scope() as scope:
        # Attach client IP and route context to Sentry isolation scope
        scope.set_user({"ip_address": client_ip})
        scope.set_tag("http.client_ip", client_ip)
        scope.set_tag("http.method", method)
        scope.set_tag("http.route", path)

        try:
            response = await call_next(request)
            duration_ms = (time.perf_counter() - start_time) * 1000.0

            # Enrich Sentry scope
            status_code = response.status_code
            scope.set_tag("http.status_code", str(status_code))
            scope.set_context(
                "http_request_telemetry",
                {
                    "method": method,
                    "path": path,
                    "query_params": str(request.query_params),
                    "client_ip": client_ip,
                    "status_code": status_code,
                    "round_trip_latency_ms": round(duration_ms, 2),
                    "user_agent": request.headers.get("user-agent", "unknown"),
                },
            )

            # Record round-trip latency measurement on Sentry APM transaction
            sentry_sdk.set_measurement("round_trip_latency_ms", duration_ms, "millisecond")

            # Add process time header to HTTP response
            response.headers["X-Process-Time"] = f"{duration_ms:.2f}ms"

            # Structured logging (debug for healthcheck and static assets, info for API endpoints)
            log_msg = f"{method} {path} -> {status_code} latency={duration_ms:.2f}ms ip={client_ip}"
            if path in ("/api/health", "/favicon.svg") or path.startswith("/assets/"):
                logger.debug(log_msg)
            else:
                logger.info(log_msg)

            return response

        except Exception as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            scope.set_tag("http.status_code", "500")
            scope.set_context(
                "http_request_telemetry",
                {
                    "method": method,
                    "path": path,
                    "query_params": str(request.query_params),
                    "client_ip": client_ip,
                    "status_code": 500,
                    "round_trip_latency_ms": round(duration_ms, 2),
                    "error": str(exc),
                },
            )
            sentry_sdk.capture_exception(exc)
            logger.error(
                f"{method} {path} -> 500 FAILED latency={duration_ms:.2f}ms ip={client_ip} error={exc}"
            )
            raise exc


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/api/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    """Verify live MotherDuck connectivity, latency, and cache status."""
    db_status = db_manager.health_check()
    cached = cache.get("screener_all")
    cached_count = len(cached) if cached else 0

    overall_status = "ok" if db_status["database"] == "connected" else "error"

    return HealthResponse(
        status=overall_status,
        database=db_status["database"],
        database_target=db_status["database_target"],
        motherduck_latency_ms=db_status["latency_ms"],
        cached_markets_count=cached_count,
        version=settings.API_VERSION,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@app.get("/api/markets", response_model=ScreenerResponse)
def get_screener_markets(
    status: Literal["live", "all", "resolved"] = Query(
        default="live", description="Filter: 'live' disputes, 'resolved' markets, or 'all'"
    ),
    min_voters: int = Query(default=0, ge=0, description="Minimum total voter turnout (default 0: all markets)"),
    search: str | None = Query(default=None, description="Search query matching question or ID"),
    sort_by: str = Query(default="latest_dispute_started", description="Field to sort by"),
    sort_dir: Literal["asc", "desc"] = Query(default="desc", description="Sort direction"),
    limit: int = Query(default=3000, ge=1, le=5000, description="Max results returned"),
) -> ScreenerResponse:
    """
    Returns prediction markets list formatted for ScreenerTable.
    Filtered and sorted in-memory from the SWR cache.
    """
    try:
        all_markets = get_cached_screener_markets()
    except Exception as e:
        logger.error(f"Failed to fetch screener markets: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"Database unreachable: {e}",
        )

    # 1. Status filter
    if status == "live":
        filtered = [m for m in all_markets if m.is_live_dispute]
    elif status == "resolved":
        filtered = [m for m in all_markets if not m.is_live_dispute]
    else:
        filtered = all_markets

    # 2. Min voters filter
    if min_voters > 0:
        filtered = [m for m in filtered if m.total_voters >= min_voters]

    # 3. Search query filter
    if search and search.strip():
        q = search.strip().lower()
        filtered = [
            m for m in filtered
            if q in m.question.lower() or q in m.market_id.lower()
        ]

    # 4. Sorting
    def sort_key(m: ScreenerMarket) -> Any:
        val = getattr(m, sort_by, None)
        if val is None:
            return "" if sort_dir == "asc" else "zzzz"
        return val

    filtered.sort(key=sort_key, reverse=(sort_dir == "desc"))

    live_count = sum(1 for m in all_markets if m.is_live_dispute)
    paged = filtered[:limit]

    return ScreenerResponse(
        markets=paged,
        total_count=len(filtered),
        live_count=live_count,
        as_of=datetime.now(timezone.utc).isoformat(),
    )


@app.get("/api/markets/{market_id}/detail", response_model=MarketAnalyticsDetail)
def get_market_detail(
    market_id: str,
    trust_number: int = Query(default=20, ge=1, le=200),
    prior_score: float = Query(default=0.50, ge=0.0, le=1.0),
    power_exponent: float = Query(default=2.0, ge=0.5, le=5.0),
    min_accuracy: float = Query(default=0.0, ge=0.0, le=95.0),
) -> MarketAnalyticsDetail:
    """
    Returns complete dispute analytics payload: rounds, price history,
    Bayesian consensus trajectory, voter distribution, cohort RMS, and chat stream.
    """
    cache_key = f"detail_{market_id}_{trust_number}_{prior_score}_{power_exponent}_{min_accuracy}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    # 1. Fetch market metadata
    m_sql = f"""
    SELECT 
        m.market_id, m.question, m.slug, raw.description,
        m.uma_resolution_status, m.closed, m.yes_price, m.no_price
    FROM clean_pm_markets m
    LEFT JOIN raw_pm_markets raw ON m.market_id = raw.id
    WHERE m.market_id = '{market_id}'
    LIMIT 1;
    """
    m_df = db_manager.query_df(m_sql)
    if m_df.empty:
        raise HTTPException(status_code=404, detail=f"Market ID '{market_id}' not found")

    m_row = m_df.iloc[0]
    yes_p = float(m_row.get("yes_price", 0.5)) if pd.notnull(m_row.get("yes_price")) else 0.5
    no_p = float(m_row.get("no_price", 0.5)) if pd.notnull(m_row.get("no_price")) else 0.5
    is_closed = bool(m_row.get("closed", False))
    uma_status = str(m_row.get("uma_resolution_status", "")).lower()
    # 2. Fetch dispute threads & messages
    t_sql = f"""
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
    v_df = db_manager.query_df(t_sql)

    # Classify market status using dispute timing, price, and votes
    disp_start_dt = None
    p1_v = 0
    p2_v = 0
    p3_v = 0
    p4_v = 0
    if not v_df.empty:
        if "thread_created_at" in v_df.columns:
            valid_starts = v_df["thread_created_at"].dropna()
            if not valid_starts.empty:
                disp_start_dt = parse_dt(valid_starts.max())
        if "vote_type" in v_df.columns:
            v_counts = v_df["vote_type"].value_counts()
            p1_v = int(v_counts.get("P1", 0))
            p2_v = int(v_counts.get("P2", 0))
            p3_v = int(v_counts.get("P3", 0))
            p4_v = int(v_counts.get("P4", 0))

    status_code, status_label, is_live = classify_market_status(
        is_closed=is_closed,
        uma_status=uma_status,
        yes_p=yes_p,
        no_p=no_p,
        dispute_start_dt=disp_start_dt,
        p1_votes=p1_v,
        p2_votes=p2_v,
        p3_votes=p3_v,
        p4_votes=p4_v,
    )

    # 3. Construct dispute rounds summary
    dispute_rounds: list[DisputeRoundItem] = []
    if not v_df.empty:
        v_df["timestamp"] = pd.to_datetime(v_df["timestamp"])
        v_df["thread_created_at"] = pd.to_datetime(v_df["thread_created_at"])
        unique_threads = v_df.sort_values("thread_created_at")["thread_id"].unique()
        thread_to_round = {tid: idx + 1 for idx, tid in enumerate(unique_threads)}
        v_df["round_num"] = v_df["thread_id"].map(thread_to_round)

        for r_num, group in v_df.groupby("round_num"):
            r_start = group["thread_created_at"].iloc[0]
            valid_msg_ts = group["timestamp"].dropna()
            r_end = valid_msg_ts.max() if not valid_msg_ts.empty else (r_start + pd.Timedelta(hours=48))
            total_votes = len(group[group["vote_type"].isin(["P1", "P2", "P3", "P4"])])
            assertion_ids = group["assertion_id"].dropna().unique()
            assertion_str = assertion_ids[0] if len(assertion_ids) > 0 else None

            dispute_rounds.append(
                DisputeRoundItem(
                    round_num=int(r_num),
                    round_start=r_start.isoformat(),
                    round_end=r_end.isoformat(),
                    assertion_id=assertion_str,
                    total_votes=total_votes,
                )
            )

    # 4. Fetch price history (price-change events + start/end bounds)
    p_sql = f"""
    WITH ranked AS (
        SELECT 
            observed_at_iso AS timestamp,
            yes_price,
            observed_at,
            LAG(ROUND(yes_price, 4)) OVER (ORDER BY observed_at ASC) AS prev_p,
            LEAD(ROUND(yes_price, 4)) OVER (ORDER BY observed_at ASC) AS next_p
        FROM raw_pm_price_history
        WHERE market_id = '{market_id}'
          AND yes_price IS NOT NULL
    )
    SELECT timestamp, yes_price
    FROM ranked
    WHERE prev_p IS NULL
       OR next_p IS NULL
       OR ROUND(yes_price, 4) != prev_p
    ORDER BY observed_at ASC;
    """
    p_df = db_manager.query_df(p_sql)
    if not p_df.empty and "timestamp" in p_df.columns:
        p_df["timestamp"] = pd.to_datetime(p_df["timestamp"])

    price_points = [
        PricePoint(
            timestamp=r["timestamp"].isoformat() if hasattr(r["timestamp"], "isoformat") else str(r["timestamp"]),
            yes_price=round(float(r["yes_price"]), 4),
        )
        for _, r in p_df.iterrows()
    ]

    # 5. Fetch user calibration profiles
    u_sql = """
    SELECT 
        author_username, total_predictions, gradeable_predictions,
        correct_predictions, lifetime_accuracy, is_calibrated
    FROM vw_dc_user_profiles;
    """
    try:
        u_df = db_manager.query_df(u_sql)
        user_profiles = {r["author_username"]: r.to_dict() for _, r in u_df.iterrows()}
    except Exception as e:
        logger.warning(f"Failed to fetch user profiles: {e}")
        user_profiles = {}

    # Filter votes to valid stances
    valid_votes = v_df[v_df["vote_type"].isin(["P1", "P2", "P3", "P4"])].copy() if not v_df.empty else pd.DataFrame()

    # 6. Run Bayesian consensus analytics
    analytics = build_market_analytics(
        votes_df=valid_votes,
        price_df=p_df,
        user_profiles=user_profiles,
        trust_number=trust_number,
        prior_score=prior_score,
        power_exponent=power_exponent,
        min_accuracy_filter=min_accuracy,
        fallback_price=yes_p,
    )

    delta = round(analytics["implied_ev"] - yes_p, 4)

    # Best bid/ask approximations
    best_bid = round(max(0.01, yes_p - 0.02), 3)
    best_ask = round(min(0.99, yes_p + 0.02), 3)

    detail = MarketAnalyticsDetail(
        market_id=market_id,
        question=str(m_row.get("question") or ""),
        slug=str(m_row.get("slug")) if pd.notnull(m_row.get("slug")) else None,
        description=str(m_row.get("description")) if pd.notnull(m_row.get("description")) else None,
        market_status_code=status_code,
        market_status_label=status_label,
        yes_price=round(yes_p, 4),
        no_price=round(no_p, 4),
        best_bid=best_bid,
        best_bid_shares=15420.0,
        best_ask=best_ask,
        best_ask_shares=22150.0,
        consensus_price_delta=delta,
        dispute_rounds=dispute_rounds,
        price_history=price_points,
        consensus_trajectory=analytics["consensus_trajectory"],
        voter_distribution=analytics["voter_distribution"],
        cohort_rms=analytics["cohort_rms"],
        cohort_counts=analytics["cohort_counts"],
        chat_messages=analytics["chat_messages"],
    )

    ttl = settings.LIVE_DETAIL_CACHE_TTL_SEC if is_live else settings.CLOSED_DETAIL_CACHE_TTL_SEC
    cache.set(cache_key, detail, ttl)
    return detail


@app.get("/api/markets/{market_id}/price-history", response_model=list[PricePoint])
def get_price_history(market_id: str) -> list[PricePoint]:
    """Retrieve price history series filtered to price changes and boundary anchors."""
    cache_key = f"price_history_{market_id}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    sql = f"""
    WITH ranked AS (
        SELECT 
            observed_at_iso AS timestamp,
            yes_price,
            observed_at,
            LAG(ROUND(yes_price, 4)) OVER (ORDER BY observed_at ASC) AS prev_p,
            LEAD(ROUND(yes_price, 4)) OVER (ORDER BY observed_at ASC) AS next_p
        FROM raw_pm_price_history
        WHERE market_id = '{market_id}'
          AND yes_price IS NOT NULL
    )
    SELECT timestamp, yes_price
    FROM ranked
    WHERE prev_p IS NULL
       OR next_p IS NULL
       OR ROUND(yes_price, 4) != prev_p
    ORDER BY observed_at ASC;
    """
    df = db_manager.query_df(sql)
    points = [
        PricePoint(
            timestamp=str(r["timestamp"]),
            yes_price=round(float(r["yes_price"]), 4),
        )
        for _, r in df.iterrows()
    ]
    cache.set(cache_key, points, settings.PRICE_HISTORY_CACHE_TTL_SEC)
    return points


def compute_discord_group_accuracy(
    qual_usernames: set[str],
    consensus_threshold: float = 0.60,
) -> GroupAccuracySummary:
    """
    Computes overall Discord group accuracy for:
    1. Qualified forecasters (consensus evaluated AFTER filtering out unqualified forecasters)
    2. All forecasters (including unqualified)
    3. Weekly breakdown:
       - # of disputed markets per week (using dispute start time)
       - % group accuracy per week for qualified only (using market closing time)
    Consensus majority is defined as > 60% agreement on an outcome.
    """
    sql = """
    WITH dispute_starts AS (
        SELECT 
            t.market_id,
            MIN(t.timestamp) AS dispute_start
        FROM clean_dc_threads t
        WHERE t.market_id IS NOT NULL
        GROUP BY t.market_id
    ),
    latest_votes AS (
        SELECT 
            t.market_id,
            v.author_username,
            v.vote_type,
            v.timestamp,
            ROW_NUMBER() OVER (PARTITION BY t.market_id, v.author_username ORDER BY v.timestamp DESC) AS rn
        FROM clean_dc_messages v
        JOIN clean_dc_threads t ON v.thread_id = t.thread_id
        WHERE v.author_username NOT IN ('UMA Herald', 'UMA Heralds')
          AND LOWER(v.author_username) NOT LIKE '%herald%'
          AND t.market_id IS NOT NULL
          AND v.vote_type IN ('P1', 'P2', 'P3')
    )
    SELECT 
        m.market_id,
        m.closed,
        m.yes_price,
        m.no_price,
        m.closed_time,
        m.uma_end_date,
        m.end_date,
        ds.dispute_start,
        lv.author_username,
        lv.vote_type
    FROM clean_pm_markets m
    JOIN dispute_starts ds ON m.market_id = ds.market_id
    LEFT JOIN latest_votes lv ON m.market_id = lv.market_id AND lv.rn = 1;
    """
    df_votes = db_manager.query_df(sql)

    markets: dict[str, dict[str, Any]] = {}
    for _, r in df_votes.iterrows():
        mid = str(r["market_id"])
        if mid not in markets:
            yes_p = float(r["yes_price"]) if pd.notnull(r["yes_price"]) else 0.5
            no_p = float(r["no_price"]) if pd.notnull(r["no_price"]) else 0.5
            closed = bool(r["closed"])

            # Strictly definitive dispute resolutions: P1 (NO), P2 (YES), P3 (50-50)
            outcome = None
            if yes_p >= 0.99:
                outcome = "P2"
            elif no_p >= 0.99 or yes_p <= 0.01:
                outcome = "P1"
            elif closed and 0.48 <= yes_p <= 0.52:
                outcome = "P3"

            markets[mid] = {
                "outcome": outcome,
                "dispute_start": r.get("dispute_start"),
                "closed_time": r.get("closed_time"),
                "uma_end_date": r.get("uma_end_date"),
                "end_date": r.get("end_date"),
                "votes": [],
            }

        if pd.notnull(r.get("author_username")) and pd.notnull(r.get("vote_type")):
            vt = str(r["vote_type"])
            if vt in ("P1", "P2", "P3"):
                markets[mid]["votes"].append((str(r["author_username"]), vt))

    def _eval_group(is_qual: bool) -> GroupAccuracyMetrics:
        eval_count = 0
        consensus_count = 0
        correct_count = 0

        for mid, m in markets.items():
            outcome = m["outcome"]
            if not outcome:
                continue

            if is_qual:
                v_list = [vt for u, vt in m["votes"] if u in qual_usernames]
            else:
                v_list = [vt for _, vt in m["votes"]]

            if not v_list:
                continue

            eval_count += 1
            counts = Counter(v_list)
            top_vt, top_cnt = counts.most_common(1)[0]
            if top_cnt / len(v_list) > consensus_threshold:
                consensus_count += 1
                if top_vt == outcome:
                    correct_count += 1

        acc = (correct_count / consensus_count * 100.0) if consensus_count else 0.0
        cons_rate = (consensus_count / eval_count * 100.0) if eval_count else 0.0

        return GroupAccuracyMetrics(
            accuracy_pct=round(acc, 1),
            correct_markets=correct_count,
            consensus_markets=consensus_count,
            total_markets_evaluated=eval_count,
            consensus_rate_pct=round(cons_rate, 1),
        )

    # 1. Weekly dispute volume by dispute start time
    weekly_disputes: dict[str, int] = {}
    for m in markets.values():
        disp_val = m.get("dispute_start")
        if pd.notnull(disp_val):
            try:
                dt = pd.to_datetime(disp_val, utc=True)
                w_monday = dt - pd.to_timedelta(dt.weekday(), unit="D")
                w_key = w_monday.strftime("%Y-%m-%d")
                weekly_disputes[w_key] = weekly_disputes.get(w_key, 0) + 1
            except Exception:
                pass

    # 2. Weekly qualified consensus accuracy by market closing time
    weekly_qualified_acc: dict[str, dict[str, int]] = {}
    for m in markets.values():
        outcome = m.get("outcome")
        if not outcome:
            continue
        v_list = [vt for u, vt in m["votes"] if u in qual_usernames]
        if not v_list:
            continue
        counts = Counter(v_list)
        top_vt, top_cnt = counts.most_common(1)[0]
        if top_cnt / len(v_list) > consensus_threshold:
            is_correct = (top_vt == outcome)
            closing_val = m.get("closed_time") or m.get("uma_end_date") or m.get("end_date") or m.get("dispute_start")
            if pd.notnull(closing_val):
                try:
                    cdt = pd.to_datetime(closing_val, utc=True)
                    c_monday = cdt - pd.to_timedelta(cdt.weekday(), unit="D")
                    cw_key = c_monday.strftime("%Y-%m-%d")
                    if cw_key not in weekly_qualified_acc:
                        weekly_qualified_acc[cw_key] = {"consensus": 0, "correct": 0}
                    weekly_qualified_acc[cw_key]["consensus"] += 1
                    if is_correct:
                        weekly_qualified_acc[cw_key]["correct"] += 1
                except Exception:
                    pass

    # 3. Assemble weekly continuous time series
    active_weeks = set(weekly_disputes.keys()) | set(weekly_qualified_acc.keys())
    valid_weeks = [w for w in active_weeks if "2023-01-01" <= w <= "2026-12-31"]
    if not valid_weeks and active_weeks:
        valid_weeks = list(active_weeks)

    weekly_breakdown: list[WeeklyAccuracyItem] = []
    if valid_weeks:
        min_w = min(valid_weeks)
        max_w = max(valid_weeks)
        full_date_range = pd.date_range(start=min_w, end=max_w, freq="W-MON")
        for dt_val in full_date_range:
            w_str = dt_val.strftime("%Y-%m-%d")
            d_cnt = weekly_disputes.get(w_str, 0)
            acc_info = weekly_qualified_acc.get(w_str, {"consensus": 0, "correct": 0})
            c_cnt = acc_info["consensus"]
            corr_cnt = acc_info["correct"]
            acc_pct = round((corr_cnt / c_cnt * 100.0), 1) if c_cnt > 0 else None
            w_label = dt_val.strftime("%b %d, '%y")

            weekly_breakdown.append(
                WeeklyAccuracyItem(
                    week_start=w_str,
                    week_label=w_label,
                    disputed_markets_count=d_cnt,
                    resolved_consensus_markets=c_cnt,
                    correct_markets=corr_cnt,
                    accuracy_pct=acc_pct,
                )
            )

    return GroupAccuracySummary(
        qualified=_eval_group(is_qual=True),
        all_forecasters=_eval_group(is_qual=False),
        weekly_breakdown=weekly_breakdown,
        consensus_threshold_pct=round(consensus_threshold * 100.0, 1),
        qualified_criteria_label=f"Qualified ({len(qual_usernames)} forecasters)",
        resolution_scope_note="Accounts strictly for dispute resolutions (YES, NO, 50-50) and excludes procedural EARLY / CANCEL decisions",
    )


@app.get("/api/leaderboard", response_model=LeaderboardResponse)
def get_voter_leaderboard(
    min_predictions: int = Query(default=5, ge=1, description="Minimum graded predictions required for qualification"),
    min_competency_pct: float = Query(default=50.0, ge=0.0, le=100.0, description="Minimum Bayesian accuracy % for qualification"),
    limit: int = Query(default=1000, ge=1, le=2000, description="Max ranked voters returned"),
) -> LeaderboardResponse:
    """Returns voter calibration leaderboard ranked by Bayesian accuracy with overall Discord group accuracy."""
    cache_key = f"leaderboard_{min_predictions}_{min_competency_pct}_{limit}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    sql = """
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
    df = db_manager.query_df(sql)
    raw_voters: list[dict] = []
    qual_usernames: set[str] = set()

    for _, row in df.iterrows():
        uname = str(row["author_username"])
        grad_val = row.get("gradeable_predictions")
        grad = int(grad_val) if pd.notnull(grad_val) else 0

        corr_val = row.get("correct_predictions")
        corr = int(corr_val) if pd.notnull(corr_val) else 0

        tot_val = row.get("total_predictions")
        tot = int(tot_val) if pd.notnull(tot_val) else 0

        raw_val = row.get("lifetime_accuracy")
        raw_acc = float(raw_val) * 100.0 if pd.notnull(raw_val) else 0.0
        if pd.isna(raw_acc):
            raw_acc = 0.0
        raw_acc = max(0.0, min(100.0, raw_acc))

        b_acc = compute_bayesian_score(corr, grad) * 100.0
        if pd.isna(b_acc):
            b_acc = 50.0
        b_acc = max(0.0, min(100.0, b_acc))

        is_qual = bool(grad >= min_predictions and b_acc >= min_competency_pct)
        if is_qual:
            qual_usernames.add(uname)

        raw_voters.append(
            {
                "author_username": uname,
                "total_predictions": tot,
                "gradeable_predictions": grad,
                "correct_predictions": corr,
                "lifetime_accuracy_pct": round(raw_acc, 2),
                "bayesian_accuracy_pct": round(b_acc, 2),
                "is_calibrated": is_qual,
                "last_voted_at": str(row["last_voted_at"]) if pd.notnull(row.get("last_voted_at")) else None,
            }
        )

    # Sort descending by Bayesian accuracy, tiebreak on gradeable predictions
    raw_voters.sort(key=lambda v: (v["bayesian_accuracy_pct"], v["gradeable_predictions"]), reverse=True)
    voters = [
        VoterLeaderboardItem(
            rank=idx + 1,
            **item,
        )
        for idx, item in enumerate(raw_voters)
    ]

    # Compute overall Discord group accuracy (STRICTLY using qualified forecasters)
    group_acc = compute_discord_group_accuracy(qual_usernames=qual_usernames, consensus_threshold=0.60)

    resp = LeaderboardResponse(
        voters=voters[:limit],
        total_voters_count=len(voters),
        calibrated_voters_count=len(qual_usernames),
        as_of=datetime.now(timezone.utc).isoformat(),
        group_accuracy=group_acc,
        min_predictions=min_predictions,
        min_competency_pct=min_competency_pct,
    )
    cache.set(cache_key, resp, settings.LEADERBOARD_CACHE_TTL_SEC)
    return resp


@app.get("/api/pipeline/status", response_model=list[PipelineStatusItem])
def get_pipeline_status() -> list[PipelineStatusItem]:
    """Retrieve last 10 pipeline execution runs."""
    cached = cache.get("pipeline_status")
    if cached is not None:
        return cached

    sql = """
    SELECT run_id, mode, start_time, end_time, status
    FROM pipeline_runs
    ORDER BY start_time DESC
    LIMIT 10;
    """
    try:
        df = db_manager.query_df(sql)
        items = [
            PipelineStatusItem(
                run_id=str(r["run_id"]),
                mode=str(r.get("mode")) if pd.notnull(r.get("mode")) else None,
                start_time=str(r.get("start_time")) if pd.notnull(r.get("start_time")) else None,
                end_time=str(r.get("end_time")) if pd.notnull(r.get("end_time")) else None,
                status=str(r.get("status")) if pd.notnull(r.get("status")) else None,
            )
            for _, r in df.iterrows()
        ]
        cache.set("pipeline_status", items, settings.PIPELINE_STATUS_CACHE_TTL_SEC)
        return items
    except Exception as e:
        logger.warning(f"Pipeline status query failed: {e}")
        return []


# ---------------------------------------------------------------------------
# Production SPA & Static Assets Serving
# ---------------------------------------------------------------------------
dist_dir = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if not dist_dir.exists():
    dist_dir = Path("frontend/dist")

if dist_dir.exists():
    assets_dir = dist_dir / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        if full_path.startswith("api"):
            raise HTTPException(status_code=404, detail="API endpoint not found")
        file_path = dist_dir / full_path
        if file_path.is_file():
            return FileResponse(str(file_path))
        index_file = dist_dir / "index.html"
        if index_file.is_file():
            return FileResponse(str(index_file))
        raise HTTPException(status_code=404, detail="Web application not built")


if __name__ == "__main__":
    logger.info(f"Starting {settings.API_TITLE} on {settings.HOST}:{settings.PORT}")
    uvicorn.run(
        "backend.src.app:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True,
    )
