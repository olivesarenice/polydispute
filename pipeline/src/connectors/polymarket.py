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
    end_date: Optional[str] = None
    start_date: Optional[str] = None
    description: Optional[str] = None
    outcomes: Optional[str] = None
    outcome_prices: Optional[str] = None
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
    # CLOB token IDs — JSON string '["<yes_token>","<no_token>"]'
    # Required to query clob.polymarket.com/prices-history (takes asset/token ID, not market ID)
    clob_token_ids: Optional[str] = Field(default=None, alias="clobTokenIds")

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

    def get_market_by_id(self, market_id: str) -> PolymarketMarket | None:
        """
        Fetch a single market by its numeric ID via the single-resource endpoint.

        Unlike GET /markets?id[]=..., this endpoint returns archived/old markets
        that the bulk list endpoint silently omits.
        Returns None if the market is not found or fails to parse.
        """
        try:
            raw = self._get(f"markets/{market_id}")
            return PolymarketMarket(**raw)
        except Exception as e:
            logger.warning(f"Failed to fetch market {market_id}: {e}")
            return None

    def get_markets_by_ids(
        self,
        market_ids: list[str],
        max_workers: int = 25,
    ) -> list[PolymarketMarket]:
        """
        Fetch multiple markets by ID in parallel using the single-resource endpoint.

        Uses ThreadPoolExecutor with max_workers=25 to stay safely under the
        /markets rate limit of 300 req/10s (30 req/s). At 25 concurrent workers
        and ~30-50ms round-trip each, effective throughput is ~20 req/s.

        Results are returned in input order. IDs that return None (not found /
        deleted upstream) are silently dropped — the caller sees only valid markets.
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        if not market_ids:
            return []

        results: dict[str, PolymarketMarket | None] = {}

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            future_to_id = {
                pool.submit(self.get_market_by_id, mid): mid
                for mid in market_ids
            }
            for future in as_completed(future_to_id):
                mid = future_to_id[future]
                try:
                    results[mid] = future.result()
                except Exception as e:
                    logger.error(f"Unexpected error fetching market {mid}: {e}")
                    results[mid] = None

        found = [results[mid] for mid in market_ids if results.get(mid) is not None]
        not_found = sum(1 for mid in market_ids if results.get(mid) is None)
        logger.info(
            f"get_markets_by_ids: {len(found)} fetched, "
            f"{not_found} not found — out of {len(market_ids)} requested."
        )
        return found


class ClobClient:
    """
    Client for the Polymarket CLOB API (clob.polymarket.com).
    Used for price history — takes CLOB token IDs (not market IDs).
    Rate limit: same /markets endpoint family, 300 req/10s.
    """
    def __init__(self, base_url: str = "https://clob.polymarket.com"):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()

    def _get(self, endpoint: str, params: dict = None) -> Any:
        url = f"{self.base_url}/{endpoint}"
        logger.debug(f"GET {url} params={params}")
        try:
            response = self.session.get(url, params=params, timeout=15)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"CLOB API request failed on {endpoint}: {e}")
            raise

    def get_prices_history(
        self,
        token_id: str,
        interval: str = "max",
        fidelity: int = 60,
        start_ts: int | None = None,
        end_ts: int | None = None,
    ) -> list[dict]:
        """
        Fetch price history for a single CLOB token (YES or NO side of a market).

        Args:
            token_id: The CLOB asset token ID (first element of clobTokenIds = YES).
            interval:  max | all | 1m | 1w | 1d | 6h | 1h
            fidelity:  Resolution in minutes (default 60 = hourly points).
            start_ts:  Unix timestamp lower bound (inclusive).
            end_ts:    Unix timestamp upper bound (inclusive).

        Returns:
            List of dicts: [{"t": unix_ts, "p": float}, ...]
        """
        params: dict = {"market": token_id, "interval": interval, "fidelity": fidelity}
        if start_ts is not None:
            params["startTs"] = start_ts
        if end_ts is not None:
            params["endTs"] = end_ts

        data = self._get("prices-history", params=params)
        return data.get("history", [])
