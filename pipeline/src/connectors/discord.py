import os
from typing import Any, Dict, List, Optional
import requests
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field, model_validator

class DiscordThread(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: str
    parent_channel_id: str = Field(alias="channel_id")
    content: str
    timestamp: str
    
    author_id: str = ""
    author_username: str = ""
    
    embeds: List[Dict[str, Any]] = Field(default_factory=list)
    thread_metadata: Optional[Dict[str, Any]] = Field(default=None, alias="thread")

    @model_validator(mode="before")
    @classmethod
    def flatten_author(cls, data: Any) -> Any:
        if isinstance(data, dict) and "author" in data:
            author = data.get("author", {})
            data["author_id"] = author.get("id", "")
            data["author_username"] = author.get("username", "")
        return data

class DiscordMessage(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: str
    thread_id: str = Field(alias="channel_id")
    content: str
    timestamp: str
    
    author_id: str = ""
    author_username: str = ""
    embeds: List[Dict[str, Any]] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def flatten_author(cls, data: Any) -> Any:
        if isinstance(data, dict) and "author" in data:
            author = data.get("author", {})
            data["author_id"] = author.get("id", "")
            data["author_username"] = author.get("username", "")
        return data


class DiscordClient:
    """
    SDK-style client for the Discord API, strictly optimized for parsing 
    messages and threads used in the Polydispute Tier 2 signal model.
    """

    def __init__(self):
        self.auth_token = os.getenv("DISCORD_AUTH_TOKEN")
        if not self.auth_token:
            raise ValueError("DISCORD_AUTH_TOKEN environment variable required")

        self.base_url = "https://discord.com/api/v9"
        self.session = requests.Session()
        self.session.headers.update({"authorization": self.auth_token})

    def _get(self, endpoint: str, params: dict = None) -> Any:
        url = f"{self.base_url}/{endpoint}"
        logger.debug(f"GET {url}")
        try:
            response = self.session.get(url, params=params, timeout=15)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Discord API request failed on {endpoint}: {e}")
            raise

    def get_thread_starters(self, channel_id: str, limit: int = 5000, t0_str: str = None, t1_str: str = None) -> List[DiscordThread]:
        """
        Fetch thread creation messages (type=18) in a channel, filtered by t0 and t1.
        """
        from datetime import datetime, timezone
        
        t0_dt = None
        t1_dt = None
        
        if t0_str:
            if "T" not in t0_str: t0_str += "T00:00:00+00:00"
            t0_dt = datetime.fromisoformat(t0_str.replace("Z", "+00:00"))
            if t0_dt.tzinfo is None: t0_dt = t0_dt.replace(tzinfo=timezone.utc)
            
        if t1_str:
            if "T" not in t1_str: t1_str += "T00:00:00+00:00"
            t1_dt = datetime.fromisoformat(t1_str.replace("Z", "+00:00"))
            if t1_dt.tzinfo is None: t1_dt = t1_dt.replace(tzinfo=timezone.utc)

        message_type = 18
        page_size = 100

        endpoint = f"channels/{channel_id}/messages"
        params = {"limit": page_size, "message_type": message_type}

        responses = []
        while True:
            data = self._get(endpoint, params=params)
            if len(data) == 0:
                break
            
            oldest_msg_dt = datetime.fromisoformat(data[-1]["timestamp"])
            if oldest_msg_dt.tzinfo is None:
                oldest_msg_dt = oldest_msg_dt.replace(tzinfo=timezone.utc)

            for msg in data:
                msg_dt = datetime.fromisoformat(msg["timestamp"])
                if msg_dt.tzinfo is None:
                    msg_dt = msg_dt.replace(tzinfo=timezone.utc)
                    
                if t1_dt and msg_dt >= t1_dt:
                    continue
                if t0_dt and msg_dt < t0_dt:
                    continue
                    
                responses.append(msg)

            if len(responses) >= limit:
                break
                
            if t0_dt and oldest_msg_dt < t0_dt:
                logger.info(f"Reached messages older than t0 ({t0_dt}). Stopping pagination.")
                break
            
            # Pagination via 'before' cursor
            params["before"] = data[-1]["id"]

        parsed_threads = []
        for raw in responses:
            if raw.get("type") == message_type:
                try:
                    parsed_threads.append(DiscordThread(**raw))
                except Exception as e:
                    logger.warning(f"Failed to parse thread starter {raw.get('id')}: {e}")

        logger.info(f"Fetched {len(parsed_threads)} thread starters from channel {channel_id}")
        return parsed_threads[:limit]

    def get_messages(self, thread_id: str, limit: int = 100) -> List[DiscordMessage]:
        """
        Fetch messages inside a specific thread.
        """
        endpoint = f"channels/{thread_id}/messages"
        data = self._get(endpoint, params={"limit": limit})

        parsed_messages = []
        for raw in data:
            try:
                parsed_messages.append(DiscordMessage(**raw))
            except Exception as e:
                logger.warning(f"Failed to parse Discord message {raw.get('id')}: {e}")

        logger.info(f"Fetched {len(parsed_messages)} messages from thread {thread_id}")
        return parsed_messages

    def get_active_thread_ids(self, guild_id: str, parent_channel_id: str) -> List[str]:
        """
        Fetch active threads in the guild, filtered by the parent channel.
        Used to sync new messages for old, still-active disputes.
        """
        endpoint = f"guilds/{guild_id}/threads/active"
        # Discord's active threads endpoint doesn't strictly support pagination like messages, 
        # it returns up to 1000 active threads for the guild.
        data = self._get(endpoint)
        threads_raw = data.get("threads", [])
        
        thread_ids = [
            t["id"] for t in threads_raw 
            if str(t.get("parent_id")) == str(parent_channel_id)
        ]
        
        logger.info(f"Found {len(thread_ids)} active threads for channel {parent_channel_id}")
        return thread_ids
