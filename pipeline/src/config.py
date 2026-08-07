# pipeline/src/config.py
import os


class DiscordConfig:
    # UMA guild ID
    DISPUTES_GUILD_ID = "718590743446290492"
    # UMA #disputes channel ID
    DISPUTES_CHANNEL_ID = "964000735073284127"
    DEFAULT_LIMIT = 100


class PolygonConfig:
    # Default CTF adapter address if none is provided by PM
    DEFAULT_CTF_ADAPTER = "0x65070BE91477460D8A7AeEb94ef92fe056C2f2A7"


class PipelineConfig:
    # Use absolute paths based on this file's location to ensure robust execution
    BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

    DB_PATH = os.path.join(BASE_DIR, "pipeline", "data", "polydispute.db")
    TMP_DATA_DIR = os.path.join(BASE_DIR, "pipeline", "data", "tmp")
    RAW_STAGING_DIR = os.path.join(BASE_DIR, "pipeline", "data", "raw")

    # Tier 2 calibration: users with fewer than this many graded (P1/P2) votes
    # on resolved markets get weight=0 in the tau computation.
    MIN_CALIBRATION_VOTES: int = 5

    # System/bot accounts excluded from vote scoring.
    # UMA Herald opens every dispute thread with a templated message that
    # contains all four vote labels — it is not casting a prediction.
    SYSTEM_USERNAMES: frozenset[str] = frozenset({"UMA Herald"})
