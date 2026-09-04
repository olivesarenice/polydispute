"""MotherDuck database connection manager for Polydispute backend.

Features:
- Thread-safe query execution via DuckDB cursors and connection locks.
- Tenacity exponential backoff retries on transient connection exceptions.
- Health check ping and query latency telemetry.
- Graceful reconnection and error handling.
"""

import threading
import time
from typing import Any

import duckdb
import pandas as pd
from loguru import logger
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from backend.src.config import settings


class MotherDuckManager:
    """Thread-safe singleton managing connections to MotherDuck cloud warehouse."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._conn: duckdb.DuckDBPyConnection | None = None
        self._last_ping_latency_ms: float = 0.0

    def _get_token(self) -> str:
        """Retrieve token from settings or environment."""
        token = settings.MOTHERDUCK_TOKEN
        if not token:
            import os
            token = os.getenv("MOTHERDUCK_TOKEN")
        if not token or token.startswith("md_..."):
            raise ValueError(
                "MOTHERDUCK_TOKEN is required to connect to MotherDuck. "
                "Ensure Doppler secrets or MOTHERDUCK_TOKEN env var is set."
            )
        return token

    def _connect(self) -> duckdb.DuckDBPyConnection:
        """Establish connection to MotherDuck and ensure target DB exists."""
        token = self._get_token()
        target_db = settings.target_database
        logger.info(f"Connecting to MotherDuck database '{target_db}'...")

        conn = duckdb.connect(f"md:?token={token}")
        conn.execute(f"CREATE DATABASE IF NOT EXISTS {target_db}")
        conn.execute(f"USE {target_db}")
        return conn

    def get_connection(self) -> duckdb.DuckDBPyConnection:
        """Return active DuckDB connection, reconnecting if disconnected."""
        with self._lock:
            if self._conn is None:
                self._conn = self._connect()
            return self._conn

    def close(self) -> None:
        """Close connection cleanly."""
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                except Exception as e:
                    logger.warning(f"Error closing MotherDuck connection: {e}")
                finally:
                    self._conn = None

    def reconnect(self) -> duckdb.DuckDBPyConnection:
        """Reset and re-establish connection."""
        self.close()
        return self.get_connection()

    def health_check(self) -> dict[str, Any]:
        """Ping database with 'SELECT 1' and measure latency in milliseconds."""
        t0 = time.perf_counter()
        try:
            conn = self.get_connection()
            with self._lock:
                cursor = conn.cursor()
                res = cursor.execute("SELECT 1").fetchone()
                cursor.close()

            latency = round((time.perf_counter() - t0) * 1000.0, 2)
            self._last_ping_latency_ms = latency

            if res and res[0] == 1:
                return {
                    "database": "connected",
                    "database_target": f"md:{settings.target_database}",
                    "latency_ms": latency,
                    "error": None,
                }
            return {
                "database": "unreachable",
                "database_target": f"md:{settings.target_database}",
                "latency_ms": latency,
                "error": "Unexpected ping response",
            }
        except Exception as e:
            latency = round((time.perf_counter() - t0) * 1000.0, 2)
            logger.warning(f"MotherDuck health check ping failed: {e}")
            return {
                "database": "unreachable",
                "database_target": f"md:{settings.target_database}",
                "latency_ms": latency,
                "error": str(e),
            }

    def query_df(self, sql: str) -> pd.DataFrame:
        """
        Execute an analytical SQL query and return results as a Pandas DataFrame.
        Includes automatic retries on transient connection exceptions.
        """
        @retry(
            retry=retry_if_exception_type((duckdb.ConnectionException, duckdb.IOException, TimeoutError)),
            stop=stop_after_attempt(settings.DB_MAX_RETRIES),
            wait=wait_exponential(
                multiplier=settings.DB_RETRY_MIN_BACKOFF,
                max=settings.DB_RETRY_MAX_BACKOFF,
            ),
            reraise=True,
        )
        def _execute_with_retry() -> pd.DataFrame:
            try:
                conn = self.get_connection()
                with self._lock:
                    cursor = conn.cursor()
                    df = cursor.execute(sql).df()
                    cursor.close()
                    return df
            except (duckdb.ConnectionException, duckdb.IOException) as conn_err:
                logger.warning(f"Connection dropped during query ({conn_err}). Reconnecting...")
                self.reconnect()
                raise

        return _execute_with_retry()


# Global database manager instance
db_manager = MotherDuckManager()
