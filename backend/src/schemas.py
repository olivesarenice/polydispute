"""Pydantic response and request schemas for the Polydispute API.

Strict field-level validation matching frontend contracts for ScreenerTable,
DisputeAnalysisPanel, ConsensusReplayPanel, and Leaderboard.
"""

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Health & Diagnostics
# ---------------------------------------------------------------------------
class HealthResponse(BaseModel):
    """Health check response for monitoring and navbar status pill."""

    status: str = Field(..., description="'ok', 'degraded', or 'error'")
    database: str = Field(..., description="'connected' or 'unreachable'")
    database_target: str = Field(
        ..., description="Target MotherDuck database (e.g. 'md:polydispute_dev')"
    )
    motherduck_latency_ms: float = Field(
        ..., ge=0.0, description="Ping query latency in milliseconds"
    )
    cached_markets_count: int = Field(
        ..., ge=0, description="Number of screener markets held in memory"
    )
    version: str = Field(..., description="API version")
    timestamp: str = Field(..., description="Current UTC timestamp")


# ---------------------------------------------------------------------------
# Screener Models
# ---------------------------------------------------------------------------
class ScreenerMarket(BaseModel):
    """Individual prediction market row formatted for ScreenerTable."""

    market_id: str = Field(
        ..., min_length=1, description="Unique Polymarket market ID"
    )
    question: str = Field(..., description="Market prediction title / question")
    slug: str | None = Field(
        default=None, description="Polymarket URL slug for direct external link"
    )
    description: str | None = Field(
        default=None, description="Official resolution criteria"
    )
    market_status_code: str = Field(
        ...,
        description="Categorical code: LIVE_DISPUTE, RESOLVED_P1, RESOLVED_P2, RESOLVED_P4, RESOLVED",
    )
    market_status_label: str = Field(
        ..., description="Human-readable status label"
    )
    is_live_dispute: bool = Field(
        ...,
        description="True if currently active dispute within SLA window and not closed",
    )
    latest_dispute_started: str | None = Field(
        default=None, description="ISO timestamp of newest dispute thread"
    )
    market_closed_time: str | None = Field(
        default=None, description="ISO timestamp of market resolution closure"
    )
    market_specified_end_time: str | None = Field(
        default=None, description="ISO timestamp of UMA specified end date"
    )
    yes_price: float = Field(
        ..., ge=0.0, le=1.0, description="Polymarket YES token price (0.00-1.00)"
    )
    no_price: float = Field(
        ..., ge=0.0, le=1.0, description="Polymarket NO token price (0.00-1.00)"
    )
    total_voters: int = Field(
        default=0, ge=0, description="Count of distinct community voters"
    )
    predominant_vote: str = Field(
        ..., description="Plurality callout, e.g. 'YES (85%)' or 'EARLY (100%)'"
    )
    p1_votes: int = Field(
        default=0, ge=0, description="Count of NO (P1) votes"
    )
    p2_votes: int = Field(
        default=0, ge=0, description="Count of YES (P2) votes"
    )
    p3_votes: int = Field(
        default=0, ge=0, description="Count of 50-50 (P3) votes"
    )
    p4_votes: int = Field(
        default=0, ge=0, description="Count of EARLY/CANCEL (P4) votes"
    )
    total_rounds: int = Field(
        default=1, ge=1, description="Number of distinct dispute rounds"
    )
    ur_committee_signal: str = Field(
        default="N/A", description="UMA Risk Committee recommendation"
    )


class ScreenerResponse(BaseModel):
    """Collection response for Screener catalog."""

    markets: list[ScreenerMarket]
    total_count: int = Field(..., ge=0)
    live_count: int = Field(..., ge=0)
    as_of: str = Field(..., description="Timestamp of data generation")


# ---------------------------------------------------------------------------
# Market Analytics & Dispute Details
# ---------------------------------------------------------------------------
class DisputeRoundItem(BaseModel):
    """Dispute round summary boundary."""

    round_num: int = Field(..., ge=1)
    round_start: str = Field(..., description="ISO timestamp of round start")
    round_end: str = Field(..., description="ISO timestamp of round end")
    assertion_id: str | None = Field(
        default=None, description="UMA assertion hash if available"
    )
    total_votes: int = Field(default=0, ge=0)


class PricePoint(BaseModel):
    """Polymarket midpoint price observation."""

    timestamp: str = Field(..., description="ISO timestamp")
    yes_price: float = Field(..., ge=0.0, le=1.0)


class TrajectoryEvent(BaseModel):
    """Time-series stepped event representing evolving Bayesian consensus."""

    timestamp: str = Field(..., description="ISO timestamp")
    author_username: str = Field(..., description="Voter username")
    vote_type: str = Field(
        ...,
        pattern=r"^(P1|P2|P3|P4)$",
        description="P1 (NO), P2 (YES), P3 (50-50), P4 (EARLY)",
    )
    yes_price: float | None = Field(
        default=None, description="Market price at this timestamp"
    )
    p1_weighted_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    p2_weighted_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    p3_weighted_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    p4_weighted_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    weighted_implied_ev: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Implied YES expected value (0.00 to 1.00)",
    )


class VoterDistributionItem(BaseModel):
    """Unique voter data point for VoterDistributionChart dot map."""

    author_username: str
    vote_type: str = Field(..., pattern=r"^(P1|P2|P3|P4)$")
    bayesian_accuracy_pct: float = Field(..., ge=0.0, le=100.0)
    power_weight: float = Field(..., ge=0.0)
    x_jitter: float = Field(
        ..., description="Deterministic horizontal jitter for chart readability"
    )


class ChatMessageItem(BaseModel):
    """Chronological Discord vote reasoning message."""

    message_id: str
    author_username: str
    timestamp: str
    vote_type: str
    content: str
    urls: list[str] = Field(default_factory=list)
    bayesian_score: float = Field(..., ge=0.0, le=1.0)
    power_weight: float = Field(..., ge=0.0)


class MarketAnalyticsDetail(BaseModel):
    """Full comprehensive payload for DisputeAnalysisPanel."""

    market_id: str
    question: str
    slug: str | None = None
    description: str | None = None
    market_status_code: str
    market_status_label: str
    yes_price: float = Field(..., ge=0.0, le=1.0)
    no_price: float = Field(..., ge=0.0, le=1.0)
    best_bid: float | None = None
    best_bid_shares: float | None = None
    best_ask: float | None = None
    best_ask_shares: float | None = None
    consensus_price_delta: float | None = Field(
        default=None, description="Discrepancy: (Weighted EV - yes_price)"
    )
    dispute_rounds: list[DisputeRoundItem] = Field(default_factory=list)
    price_history: list[PricePoint] = Field(default_factory=list)
    consensus_trajectory: list[TrajectoryEvent] = Field(default_factory=list)
    voter_distribution: list[VoterDistributionItem] = Field(default_factory=list)
    cohort_rms: dict[str, float] = Field(
        default_factory=dict,
        description="Power-mean RMS accuracy per cohort {'P1', 'P2', 'P3', 'P4'}",
    )
    cohort_counts: dict[str, int] = Field(
        default_factory=dict,
        description="Headcount per cohort {'P1', 'P2', 'P3', 'P4'}",
    )
    chat_messages: list[ChatMessageItem] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Voter Calibration Leaderboard
# ---------------------------------------------------------------------------
class VoterLeaderboardItem(BaseModel):
    """Forecaster calibration row from vw_dc_user_profiles."""

    rank: int = Field(..., ge=1)
    author_username: str
    total_predictions: int = Field(..., ge=0)
    gradeable_predictions: int = Field(..., ge=0)
    correct_predictions: int = Field(..., ge=0)
    lifetime_accuracy_pct: float = Field(..., ge=0.0, le=100.0)
    bayesian_accuracy_pct: float = Field(..., ge=0.0, le=100.0)
    is_calibrated: bool
    last_voted_at: str | None = None


class GroupAccuracyMetrics(BaseModel):
    """Metrics for Discord group consensus accuracy."""

    accuracy_pct: float = Field(..., description="Percentage of consensus markets matching outcome")
    correct_markets: int = Field(..., ge=0, description="Markets where consensus matched outcome")
    consensus_markets: int = Field(..., ge=0, description="Markets where consensus majority (>60%) was reached")
    total_markets_evaluated: int = Field(..., ge=0, description="Total resolved markets evaluated")
    consensus_rate_pct: float = Field(..., description="Percentage of evaluated markets reaching >60% consensus")


class WeeklyAccuracyItem(BaseModel):
    """Weekly time-series point for dispute volume and qualified consensus accuracy."""

    week_start: str = Field(..., description="Start of week (YYYY-MM-DD)")
    week_label: str = Field(..., description="Display label for week, e.g. 'Oct 14, '24'")
    disputed_markets_count: int = Field(default=0, ge=0, description="Markets whose dispute started this week")
    resolved_consensus_markets: int = Field(default=0, ge=0, description="Markets closing this week with qualified consensus")
    correct_markets: int = Field(default=0, ge=0, description="Markets closing this week with correct qualified consensus")
    accuracy_pct: float | None = Field(default=None, description="Qualified group accuracy % for markets closing this week (null if 0 consensus)")


class GroupAccuracySummary(BaseModel):
    """Overall Discord group accuracy comparison between qualified and all forecasters."""

    qualified: GroupAccuracyMetrics
    all_forecasters: GroupAccuracyMetrics
    weekly_breakdown: list[WeeklyAccuracyItem] = Field(
        default_factory=list,
        description="Weekly breakdown of disputed markets started vs qualified consensus accuracy at closing",
    )
    consensus_threshold_pct: float = Field(default=60.0, description="Consensus threshold requirement (>60%)")
    qualified_criteria_label: str = Field(
        default="Filtered to qualified forecasters",
        description="Description of qualified forecasters filter applied",
    )
    resolution_scope_note: str = Field(
        default="Accounts strictly for dispute resolutions (YES, NO, 50-50) and excludes procedural EARLY / CANCEL decisions",
        description="Clarification on dispute resolution inclusion criteria",
    )


class LeaderboardResponse(BaseModel):
    """Collection response for Voter Calibration Leaderboard."""

    voters: list[VoterLeaderboardItem]
    total_voters_count: int = Field(..., ge=0)
    calibrated_voters_count: int = Field(..., ge=0)
    as_of: str
    group_accuracy: GroupAccuracySummary | None = None
    min_predictions: int = 5
    min_competency_pct: float = 50.0


# ---------------------------------------------------------------------------
# Pipeline Status
# ---------------------------------------------------------------------------
class PipelineStatusItem(BaseModel):
    """Historical pipeline ingestion run status."""

    run_id: str
    mode: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    status: str | None = None
