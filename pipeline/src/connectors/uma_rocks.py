import requests
from typing import Any, Dict, List
from loguru import logger


class UMARocksClient:
    """
    SDK-style client for the UMA Rocks API.
    Used for ingesting Tier 1 anchor consensus answers for DVM disputes.
    """

    API_URL = "https://uma.rocks/api/getPoolAnswers"


    def __init__(self, base_url: str = API_URL) -> None:
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Polydispute/1.0"})

    def get_pool_answers(self) -> List[Dict[str, Any]]:
        """
        Fetch pool answers (deliberated P1-P4 committee consensus stances) for disputes.

        Returns:
            List of dicts containing raw UMA Rocks signals:
            [{"ancillaryData": "0x...", "question": "...", "answer": "P1", "roundId": 10135, "time": 0, "reward": 0.0}, ...]
        """
        logger.info(f"Fetching UMA Rocks pool answers from {self.base_url}")
        try:
            response = self.session.get(self.base_url, timeout=15)
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, list):
                logger.error(f"Unexpected response format from UMA Rocks: expected list, got {type(data)}")
                return []
            logger.info(f"Successfully fetched {len(data)} UMA Rocks signals")
            return data
        except requests.RequestException as e:
            logger.error(f"Failed to fetch UMA Rocks API: {e}")
            return []
