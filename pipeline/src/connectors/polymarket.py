from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from typing import List, Optional, Any, Dict
import requests
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from loguru import logger


class PolymarketMarket(BaseModel):
    model_config = ConfigDict(extra='ignore', alias_generator=to_camel, populate_by_name=True)

    id: str
    question: Optional[str] = None
    condition_id: Optional[str] = Field(default=None, alias="conditionId")
    slug: Optional[str] = None
    resolution_source: Optional[str] = Field(default=None, alias="resolutionSource")
    end_date: Optional[str] = Field(default=None, alias="endDate")
    start_date: Optional[str] = Field(default=None, alias="startDate")
    description: Optional[str] = None
    outcomes: Optional[str] = None
    outcome_prices: Optional[str] = Field(default=None, alias="outcomePrices")
    volume_num: Optional[float] = Field(default=None, alias="volumeNum")
    active: Optional[bool] = None
    closed: Optional[bool] = None
    market_maker_address: Optional[str] = Field(default=None, alias="marketMakerAddress")
    resolved_by: Optional[str] = Field(default=None, alias="resolvedBy")
    uma_resolution_status: Optional[str] = Field(default=None, alias="umaResolutionStatus")
    uma_bond: Optional[float] = Field(default=None, alias="umaBond")
    uma_reward: Optional[float] = Field(default=None, alias="umaReward")
    custom_liveness: Optional[float] = Field(default=None, alias="customLiveness")
    neg_risk: Optional[bool] = Field(default=None, alias="negRisk")
    uma_question_id: Optional[str] = Field(default=None, alias="umaQuestionID")
    clob_token_ids: Optional[str] = Field(default=None, alias="clobTokenIds")
    closed_time: Optional[str] = Field(default=None, alias="closedTime")
    uma_end_date: Optional[str] = Field(default=None, alias="umaEndDate")
    category: Optional[str] = None
    liquidity_num: Optional[float] = Field(default=None, alias="liquidityNum")
    volume_24hr: Optional[float] = Field(default=None, alias="volume24hr")


class PolymarketEvent(BaseModel):
    model_config = ConfigDict(extra='ignore', alias_generator=to_camel, populate_by_name=True)

    id: str
    ticker: Optional[str] = None
    slug: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    start_date: Optional[str] = None
    creation_date: Optional[str] = None
    end_date: Optional[str] = None
    active: Optional[bool] = None
    closed: Optional[bool] = None
    category: Optional[str] = None
    tags: Optional[List[Dict[str, Any]]] = Field(default_factory=list)
    volume: Optional[float] = None
    markets: List[PolymarketMarket] = Field(default_factory=list)


class PolymarketPriceHistory(BaseModel):
    model_config = ConfigDict(extra='ignore', alias_generator=to_camel, populate_by_name=True)

    market_id: str
    yes_clob_token_id: str
    yes_price: float
    observed_at: int
    observed_at_iso: Optional[str] = None


PolyMarketPriceHistory = PolymarketPriceHistory


class PolymarketClient:
    """
    SDK-style client for the Polymarket Gamma API.
    Supports multithreading and configurable limit parameters (max limit=500 for /events, limit=100 for /markets).
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
        limit: int = 100,
        exclude_tags: List[int] = None
    ) -> List[PolymarketEvent]:
        """
        Fetch events (and their nested markets) within a specific date range.
        Handles API pagination via offset and limit (max limit for /events is 500).
        """
        params = {
            "start_date_min": start_date_min,
            "start_date_max": start_date_max,
            "offset": offset,
            "limit": limit
        }

        if exclude_tags:
            params["exclude_tag_id"] = exclude_tags

        try:
            raw_resp = self._get("events", params=params)
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 422:
                logger.warning(f"Reached Polymarket Gamma API offset cap at offset={offset}. Stopping pagination.")
                return []
            raise

        if isinstance(raw_resp, dict):
            raw_events = raw_resp.get("events", [])
        elif isinstance(raw_resp, list):
            raw_events = raw_resp
        else:
            raw_events = []

        parsed_events = []
        for raw in raw_events:
            if not isinstance(raw, dict):
                continue
            try:
                parsed_events.append(PolymarketEvent(**raw))
            except Exception as e:
                logger.warning(f"Failed to parse Event ID {raw.get('id', 'unknown')}: {e}")

        logger.info(f"Successfully fetched and parsed {len(parsed_events)} Polymarket events (offset={offset}, limit={limit})")
        return parsed_events

    def get_events_by_slug(self, slug: str) -> List[PolymarketEvent]:
        """Fetch Polymarket events by URL slug."""
        if not slug:
            return []
        try:
            raw_resp = self._get("events", params={"slug": slug})
            raw_events = raw_resp.get("events", raw_resp) if isinstance(raw_resp, dict) else (raw_resp if isinstance(raw_resp, list) else [])
            parsed_events = []
            for raw in raw_events:
                if isinstance(raw, dict):
                    try:
                        parsed_events.append(PolymarketEvent(**raw))
                    except Exception as e:
                        logger.warning(f"Failed to parse Event slug {slug}: {e}")
            return parsed_events
        except Exception as e:
            logger.warning(f"Failed to fetch event for slug {slug}: {e}")
            return []

    def get_markets(
        self,
        market_ids: List[str],
        limit: int = 100,
        max_threads: int = 8
    ) -> List[PolymarketMarket]:
        """
        Fetch specific markets by their IDs in chunks of limit (max limit=100) using multithreading (max_threads=8).
        """
        if not market_ids:
            return []

        chunks = [market_ids[i : i + limit] for i in range(0, len(market_ids), limit)]
        parsed_markets = []

        def _fetch_chunk(chunk: List[str]) -> List[PolymarketMarket]:
            params = {"id": chunk}
            try:
                raw_resp = self._get("markets", params=params)
                raw_markets = raw_resp.get("markets", raw_resp) if isinstance(raw_resp, dict) else (raw_resp if isinstance(raw_resp, list) else [])
                res = []
                for raw in raw_markets:
                    if isinstance(raw, dict):
                        try:
                            res.append(PolymarketMarket(**raw))
                        except Exception as e:
                            logger.warning(f"Failed to parse Market ID {raw.get('id', 'unknown')}: {e}")
                return res
            except Exception as e:
                logger.warning(f"Failed to fetch market chunk: {e}")
                return []

        with ThreadPoolExecutor(max_workers=max_threads) as executor:
            results = executor.map(_fetch_chunk, chunks)
            for res in results:
                parsed_markets.extend(res)

        logger.info(f"Successfully fetched {len(parsed_markets)} Polymarket markets via {len(chunks)} parallel chunks (max_threads={max_threads}).")
        return parsed_markets

    def get_market_by_id(self, market_id: str) -> Optional[PolymarketMarket]:
        """Fetch a single market by its numeric ID."""
        try:
            raw = self._get(f"markets/{market_id}")
            return PolymarketMarket(**raw)
        except Exception as e:
            logger.warning(f"Failed to fetch market {market_id}: {e}")
            return None

    def get_markets_by_ids(
        self,
        market_ids: list[str],
        max_workers: int = 8,
    ) -> list[PolymarketMarket]:
        """Fetch multiple markets by ID in parallel using multithreading (max_workers=8)."""
        if not market_ids:
            return []

        def _fetch(mid: str) -> Optional[PolymarketMarket]:
            return self.get_market_by_id(mid)

        results: list[PolymarketMarket] = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(_fetch, mid) for mid in market_ids]
            for f in tqdm(as_completed(futures), total=len(futures), desc="Fetching Polymarket markets"):
                res = f.result()
                if res is not None:
                    results.append(res)

        logger.info(f"Parallel fetch completed: {len(results)}/{len(market_ids)} markets retrieved (threads={max_workers}).")
        return results

    def get_event_by_id(self, event_id: str) -> Optional[PolymarketEvent]:
        """Fetch a single event (with its nested markets) by its numeric ID via GET /events/{id}."""
        try:
            raw = self._get(f"events/{event_id}")
            if isinstance(raw, dict):
                return PolymarketEvent(**raw)
            return None
        except Exception as e:
            logger.warning(f"Failed to fetch event {event_id}: {e}")
            return None

    def get_events_by_ids(
        self,
        event_ids: list[str],
        max_workers: int = 8,
    ) -> list[PolymarketEvent]:
        """Fetch multiple events by ID in parallel via GET /events/{id} (max_workers=8)."""
        if not event_ids:
            return []

        def _fetch(eid: str) -> Optional[PolymarketEvent]:
            return self.get_event_by_id(eid)

        results: list[PolymarketEvent] = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(_fetch, eid) for eid in event_ids]
            for f in futures:
                res = f.result()
                if res is not None:
                    results.append(res)

        logger.info(f"Parallel event fetch completed: {len(results)}/{len(event_ids)} events retrieved (threads={max_workers}).")
        return results


class ClobClient:
    """
    Client for Polymarket CLOB API endpoints (e.g. price history).
    """

    def __init__(self, base_url: str = "https://clob.polymarket.com"):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()

    def get_prices_history(
        self,
        token_id: str,
        start_ts: Optional[int] = None,
        end_ts: Optional[int] = None,
        fidelity: int = 1,
        interval: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetches midpoint price history series for a given CLOB asset token ID.
        Enforces Range Mode: start_ts and end_ts should be explicitly provided to fetch full historical spans.
        """
        url = f"{self.base_url}/prices-history"
        params = {"market": token_id}

        MAX_CHUNK_SEC = 14 * 86400  # 14 days

        if start_ts is not None and end_ts is not None:
            if (end_ts - start_ts) > MAX_CHUNK_SEC:
                logger.info(
                    f"Range span ({(end_ts - start_ts) / 86400:.1f} days) exceeds 14-day API cap for token {token_id}. Auto-chunking into 14-day slices..."
                )
                all_history = []
                curr_start = start_ts
                while curr_start < end_ts:
                    curr_end = min(curr_start + MAX_CHUNK_SEC, end_ts)
                    chunk_params = {
                        "market": token_id,
                        "startTs": curr_start,
                        "endTs": curr_end,
                        "fidelity": fidelity,
                    }
                    try:
                        resp = self.session.get(url, params=chunk_params, timeout=15)
                        resp.raise_for_status()
                        h = resp.json().get("history", [])
                        all_history.extend(h)
                    except Exception as e:
                        logger.warning(
                            f"Chunk fetch notice [{curr_start}..{curr_end}] for token {token_id}: {e}"
                        )
                    curr_start = curr_end + 1

                # Deduplicate by timestamp 't'
                seen_ts = set()
                dedup_history = []
                for item in all_history:
                    t_val = item.get("t")
                    if t_val not in seen_ts:
                        seen_ts.add(t_val)
                        dedup_history.append(item)
                return dedup_history
            else:
                params["startTs"] = start_ts
                params["endTs"] = end_ts
                params["fidelity"] = fidelity
        elif interval:
            logger.warning(
                f"CLOB get_prices_history called without explicit range [start_ts, end_ts] for token {token_id}. Falling back to interval={interval}."
            )
            params["interval"] = interval
            params["fidelity"] = fidelity
        else:
            logger.error(
                f"CLOB get_prices_history requires either explicit range [start_ts, end_ts] or interval parameter for token {token_id}."
            )
            return []

        try:
            resp = self.session.get(url, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            return data.get("history", [])
        except Exception as e:
            logger.error(
                f"CLOB prices-history request failed for token {token_id}: {e}"
            )
            return []
