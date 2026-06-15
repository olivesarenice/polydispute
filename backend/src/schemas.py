"""Pydantic response schemas for the Polydispute API."""

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    version: str


class DisputeSignal(BaseModel):
    """A single row from disputes_view with computed arb metrics."""
    thread_id: str
    condition_id: str | None = None
    question: str | None = None
    slug: str | None = None
    uma_resolution_status: str | None = None
    uma_bond: float | None = None
    uma_reward: float | None = None
    neg_risk: bool | None = None
    yes_price: float | None = None
    no_price: float | None = None
    p1_votes: int = 0
    p2_votes: int = 0
    p3_votes: int = 0
    p4_votes: int = 0
    total_votes: int = 0
    dominant_vote: str | None = None
    tau_yes: float | None = Field(
        default=None,
        description="Community-implied YES probability based on P1/(P1+P2) vote ratio"
    )
    arb_spread: float | None = Field(
        default=None,
        description="Absolute difference between yes_price and tau_yes"
    )


class SignalsResponse(BaseModel):
    signals: list[DisputeSignal]
    count: int


class MarketDetail(BaseModel):
    """Extended market info including resolution rules."""
    condition_id: str
    market_id: str | None = None
    question: str | None = None
    slug: str | None = None
    yes_price: float | None = None
    no_price: float | None = None
    uma_resolution_status: str | None = None
    uma_bond: float | None = None
    uma_reward: float | None = None
    neg_risk: bool | None = None
    ancillary_data_decoded: str | None = Field(
        default=None,
        description="UMA resolution rules decoded from the Polygon blockchain"
    )


class DiscordStance(BaseModel):
    """Vote breakdown for a single Discord thread linked to a market."""
    thread_id: str
    market_id: str | None = None
    p1_votes: int = 0
    p2_votes: int = 0
    p3_votes: int = 0
    p4_votes: int = 0


class StancesResponse(BaseModel):
    market_id: str
    stances: list[DiscordStance]


class PipelineStatus(BaseModel):
    run_id: str
    mode: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    status: str | None = None
