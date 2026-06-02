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
