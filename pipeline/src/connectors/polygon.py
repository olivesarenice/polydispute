import os
from typing import Optional

import requests
from loguru import logger
from pydantic import BaseModel, ConfigDict
from web3 import Web3


class UmaQuestionData(BaseModel):
    model_config = ConfigDict(extra="ignore")

    question_id: str
    adapter_address: str
    oracle_address: str
    oracle_version: str
    ancillary_data_hex: str
    ancillary_data_decoded: Optional[str] = None


class PolygonClient:
    """
    SDK-style client for interacting with Polygon RPC and Etherscan V2 API
    to pull on-chain Polymarket smart contract data.
    """

    def __init__(self):
        # Enforce Secrets Management per AGENTS.md
        self.polygonscan_api_key = os.getenv("POLYGONSCAN_API_KEY")
        if not self.polygonscan_api_key:
            raise ValueError("POLYGONSCAN_API_KEY environment variable required")

        self.rpc_url = os.getenv("POLYGON_RPC_URL", "https://polygon.drpc.org")
        self.w3 = Web3(Web3.HTTPProvider(self.rpc_url))
        self.session = requests.Session()

        # Cache for ABIs to avoid redundant API calls and rate limits
        self._abi_cache = {}

    def get_abi(self, contract_address: str) -> str:
        """Fetch verified ABI from Etherscan V2 API (Chain 137 = Polygon)."""
        checksum_addr = self.w3.to_checksum_address(contract_address)
        if checksum_addr in self._abi_cache:
            return self._abi_cache[checksum_addr]

        url = "https://api.etherscan.io/v2/api"
        params = {
            "chainid": "137",
            "module": "contract",
            "action": "getabi",
            "address": checksum_addr,
            "apikey": self.polygonscan_api_key,
        }

        logger.debug(f"Fetching ABI for {checksum_addr} from Etherscan V2 API")
        try:
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            if data.get("status") != "1":
                raise ValueError(f"ABI fetch failed: {data.get('result')}")

            self._abi_cache[checksum_addr] = data["result"]
            return self._abi_cache[checksum_addr]
        except Exception as e:
            logger.error(f"Failed to fetch ABI for {checksum_addr}: {e}")
            raise

    def get_uma_question(
        self, adapter_address: str, question_id: str
    ) -> UmaQuestionData:
        """
        Query a Polymarket CTF Adapter contract to extract the UMA Question Data,
        specifically targeting the ancillaryData payload used by the UMA Oracle.
        """
        checksum_adapter = self.w3.to_checksum_address(adapter_address)
        abi = self.get_abi(checksum_adapter)
        contract = self.w3.eth.contract(address=checksum_adapter, abi=abi)

        # Identify Oracle Version based on available functions
        oracle_address = "Unknown"
        oracle_version = "Unknown"
        try:
            oracle_address = contract.functions.umaOracle().call()
            oracle_version = "OOv2"
        except Exception:
            try:
                oracle_address = contract.functions.optimisticOracle().call()
                oracle_version = "OOv3"
            except Exception:
                pass

        logger.info(f"Fetching question {question_id} from adapter {adapter_address}")
        try:
            # getQuestion(bytes32) returns a tuple representing the Question struct
            q_id_bytes = (
                Web3.to_bytes(hexstr=question_id)
                if question_id.startswith("0x")
                else question_id.encode()
            )
            question_data = contract.functions.getQuestion(q_id_bytes).call()

            # In standard PM UmaCtfAdapters, ancillaryData is at index 11
            ancillary_data_bytes = question_data[11]
            ancillary_data_hex = f"0x{ancillary_data_bytes.hex()}"

            decoded_text = None
            try:
                decoded_text = ancillary_data_bytes.decode("utf-8")
                # Secondary heuristic for OOv3
                if "ASSERT_TRUTH" in decoded_text:
                    oracle_version = "OOv3"
            except UnicodeDecodeError:
                logger.warning(
                    f"Could not decode ancillaryData to UTF-8 for {question_id}"
                )

            logger.info(f"Successfully extracted ancillaryData for {question_id}")
            return UmaQuestionData(
                question_id=question_id,
                adapter_address=checksum_adapter,
                oracle_address=oracle_address,
                oracle_version=oracle_version,
                ancillary_data_hex=ancillary_data_hex,
                ancillary_data_decoded=decoded_text,
            )

        except Exception as e:
            logger.error(f"Failed to fetch question data on-chain: {e}")
            raise
