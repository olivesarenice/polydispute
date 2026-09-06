"""Configuration settings for Polydispute backend using Pydantic Settings."""

import os
import subprocess
from pathlib import Path
from typing import Literal

from loguru import logger
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Preserve Doppler / ambient environment precedence.
# Only query Doppler CLI if MOTHERDUCK_TOKEN is completely missing from os.environ.
if not os.getenv("MOTHERDUCK_TOKEN"):
    try:
        pipeline_dir = PROJECT_ROOT / "pipeline"
        if pipeline_dir.exists():
            token = subprocess.check_output(
                ["doppler", "secrets", "get", "MOTHERDUCK_TOKEN", "--plain"],
                cwd=str(pipeline_dir),
                text=True,
                timeout=4,
            ).strip()
            if token:
                os.environ["MOTHERDUCK_TOKEN"] = token
                logger.info("Resolved MOTHERDUCK_TOKEN from Doppler CLI")
    except Exception as e:
        logger.debug(f"Doppler token query skipped: {e}")


class Settings(BaseSettings):
    """Polydispute backend runtime configuration."""

    model_config = SettingsConfigDict(
        env_file=(
            str(PROJECT_ROOT / ".env"),
            str(PROJECT_ROOT / "pipeline" / ".env"),
        ),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database & Warehouse Configuration
    PIPELINE_ENV: Literal["dev", "prod"] = Field(
        default="dev",
        description="Deployment environment stage (dev or prod)",
    )
    MOTHERDUCK_TOKEN: str | None = Field(
        default=None,
        description="MotherDuck cloud authentication token",
    )
    MOTHERDUCK_DATABASE: str | None = Field(
        default=None,
        description="Override database name if specified",
    )
    DB_TIMEOUT_SECONDS: float = Field(
        default=15.0,
        ge=1.0,
        le=60.0,
        description="Query timeout limit in seconds",
    )
    DB_MAX_RETRIES: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Maximum reconnection retry attempts",
    )
    DB_RETRY_MIN_BACKOFF: float = Field(
        default=0.5,
        ge=0.1,
        description="Initial backoff multiplier for retries (seconds)",
    )
    DB_RETRY_MAX_BACKOFF: float = Field(
        default=3.0,
        ge=0.5,
        description="Maximum backoff ceiling for retries (seconds)",
    )

    # In-Memory Cache TTLs (seconds) - 5 minutes aligned with pipeline refresh
    SCREENER_CACHE_TTL_SEC: int = Field(
        default=300,
        ge=5,
        description="Screener markets catalog cache TTL (seconds)",
    )
    LIVE_DETAIL_CACHE_TTL_SEC: int = Field(
        default=300,
        ge=5,
        description="Live active dispute market detail cache TTL (seconds)",
    )
    CLOSED_DETAIL_CACHE_TTL_SEC: int = Field(
        default=600,
        ge=60,
        description="Resolved closed market detail cache TTL (seconds)",
    )
    LEADERBOARD_CACHE_TTL_SEC: int = Field(
        default=300,
        ge=30,
        description="Voter calibration leaderboard cache TTL (seconds)",
    )
    PIPELINE_STATUS_CACHE_TTL_SEC: int = Field(
        default=300,
        ge=5,
        description="Pipeline execution status history cache TTL (seconds)",
    )
    PRICE_HISTORY_CACHE_TTL_SEC: int = Field(
        default=300,
        ge=5,
        description="Market price history series cache TTL (seconds)",
    )

    # Analytical & Bayesian Calibration Defaults
    DEFAULT_TRUST_NUMBER: int = Field(
        default=20,
        ge=1,
        le=200,
        description="Bayesian prior pseudo-observations confidence (N)",
    )
    DEFAULT_PRIOR_SCORE: float = Field(
        default=0.50,
        ge=0.0,
        le=1.0,
        description="Prior expected accuracy for uncalibrated voters (P)",
    )
    DEFAULT_POWER_EXPONENT: float = Field(
        default=2.0,
        ge=0.5,
        le=5.0,
        description="Consensus weight power function exponent (S^p)",
    )
    DEFAULT_MIN_ACCURACY_FILTER: float = Field(
        default=0.0,
        ge=0.0,
        le=95.0,
        description="Minimum Bayesian accuracy threshold (%) for vote inclusion",
    )
    SCREENER_LOOKBACK_DAYS: int = Field(
        default=60,
        ge=7,
        le=365,
        description="Lookback window (days) for historical closed disputes",
    )
    PRICE_HISTORY_PAD_HOURS: int = Field(
        default=2,
        ge=1,
        le=24,
        description="Hours of price history padding around dispute rounds",
    )
    MAX_DISPUTE_WINDOW_HOURS: int = Field(
        default=48,
        ge=6,
        le=168,
        description="Maximum display cap duration for dispute rounds in charts",
    )

    # Server & Telemetry Options
    API_TITLE: str = "Polydispute API"
    API_VERSION: str = "3.2.0"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    CORS_ORIGINS: list[str] = ["*"]
    SENTRY_DSN: str | None = None
    SENTRY_TRACES_SAMPLE_RATE: float = 1.0
    SENTRY_PROFILES_SAMPLE_RATE: float = 0.0
    LOG_LEVEL: str = "INFO"

    @property
    def target_database(self) -> str:
        """Target database name in MotherDuck."""
        if self.MOTHERDUCK_DATABASE:
            return self.MOTHERDUCK_DATABASE
        return f"polydispute_{self.PIPELINE_ENV.lower()}"


# Global settings instance
settings = Settings()
