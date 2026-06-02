import requests
from typing import List, Optional, Any
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from loguru import logger

class PolymarketMarket(BaseModel):
    model_config = ConfigDict(extra='ignore', alias_generator=to_camel, populate_by_name=True)
    
    id: str
    question: str
    condition_id: Optional[str] = None
    slug: str
    resolution_source: Optional[str] = None
    end_date: str
    start_date: str
    description: str
    outcomes: str
    outcome_prices: str
    volume_num: Optional[float] = None
    active: bool
    closed: bool
    market_maker_address: Optional[str] = None
    resolved_by: Optional[str] = None
    uma_resolution_status: Optional[str] = None
    uma_bond: Optional[float] = None
    uma_reward: Optional[float] = None
    custom_liveness: Optional[float] = None
    neg_risk: Optional[bool] = None
    uma_question_id: Optional[str] = Field(default=None, alias="questionID")

class PolymarketEvent(BaseModel):
    model_config = ConfigDict(extra='ignore', alias_generator=to_camel, populate_by_name=True)
    
    id: str
    ticker: Optional[str] = None
    slug: str
    title: str
    description: str
    start_date: str
    creation_date: str
    end_date: str
    active: bool
    closed: bool
    markets: List[PolymarketMarket] = Field(default_factory=list)


class PolymarketClient:
    """
    SDK-style client for the Polymarket Gamma API.
    """
    def __init__(self, base_url: str = "https://gamma-api.polymarket.com"):
        self.base_url = base_url.rstrip("/")
        # Gamma API public endpoints do not strictly require authentication keys
        self.session = requests.Session()

    def _get(self, endpoint: str, params: dict = None) -> Any:
        url = f"{self.base_url}/{endpoint}"
        logger.debug(f"GET {url} params={params}")
        try:
            response = self.session.get(url, params=params, timeout=15)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Polymarket API request failed on {endpoint}: {e}")
            raise

    def get_events(
        self, 
        start_date_min: str, 
        start_date_max: str, 
        offset: int = 0, 
        limit: int = 500, 
        exclude_tags: List[int] = None
    ) -> List[PolymarketEvent]:
        """
        Fetch events (and their nested markets) within a specific date range.
        Handles API pagination via offset and limit.
        """
        params = {
            "start_date_min": start_date_min,
            "start_date_max": start_date_max,
            "offset": offset,
            "limit": limit
        }
        
        # requests library automatically handles lists as duplicate query parameters
        # e.g., exclude_tag_id=102127&exclude_tag_id=1312
        if exclude_tags:
            params["exclude_tag_id"] = exclude_tags

        raw_events = self._get("events", params=params)
        
        parsed_events = []
        for raw in raw_events:
            try:
                parsed_events.append(PolymarketEvent(**raw))
            except Exception as e:
                logger.warning(f"Failed to parse Event ID {raw.get('id', 'unknown')}: {e}")
                
        logger.info(f"Successfully fetched and parsed {len(parsed_events)} Polymarket events (offset={offset})")
        return parsed_events

    def get_markets(self, market_ids: List[str]) -> List[PolymarketMarket]:
        """Fetch specific markets by their IDs to sync live state (prices, volume)."""
        if not market_ids:
            return []
            
        params = {"id": market_ids}
        raw_markets = self._get("markets", params=params)
        
        parsed_markets = []
        for raw in raw_markets:
            try:
                parsed_markets.append(PolymarketMarket(**raw))
            except Exception as e:
                logger.warning(f"Failed to parse Market ID {raw.get('id', 'unknown')}: {e}")
                
        logger.info(f"Successfully synced {len(parsed_markets)} active Polymarket markets.")
        return parsed_markets
