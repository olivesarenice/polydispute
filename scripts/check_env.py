import os
import sys

import requests
from dotenv import load_dotenv
from loguru import logger


def check_motherduck():
    token = os.getenv("MOTHERDUCK_TOKEN")
    if not token or token.startswith("md_..."):
        logger.error("❌ MotherDuck: Token not set or still uses placeholder.")
        return False

    try:
        import duckdb

        conn = duckdb.connect(f"md:?token={token}")
        conn.execute("SELECT 1").fetchall()
        logger.success("✅ MotherDuck: Successfully connected and queried.")
        return True
    except ImportError:
        logger.warning("⚠️ MotherDuck: 'duckdb' package not installed. Cannot test.")
        return False
    except Exception as e:
        logger.error(f"❌ MotherDuck: Connection failed - {e}")
        return False


def check_discord():
    token = os.getenv("DISCORD_AUTH_TOKEN")
    if not token or token.startswith("MTA_"):
        logger.error("❌ Discord: Token not set or still uses placeholder.")
        return False

    headers = {"authorization": token}
    try:
        # Check by hitting the /users/@me endpoint
        resp = requests.get(
            "https://discord.com/api/v9/users/@me", headers=headers, timeout=10
        )
        if resp.status_code == 200:
            logger.success(
                f"✅ Discord: Successfully authenticated as {resp.json().get('username', 'Unknown')}."
            )
            return True
        else:
            logger.error(
                f"❌ Discord: Auth failed. HTTP {resp.status_code} - {resp.text}"
            )
            return False
    except Exception as e:
        logger.error(f"❌ Discord: Request failed - {e}")
        return False


def check_polygonscan():
    token = os.getenv("POLYGONSCAN_API_KEY")
    if not token or token == "placeholder_polygonscan_key_here":
        logger.error("❌ PolygonScan: API Key not set.")
        return False

    try:
        # Check by getting the latest block number on chain 137
        url = f"https://api.etherscan.io/v2/api?chainid=137&module=proxy&action=eth_blockNumber&apikey={token}"
        resp = requests.get(url, timeout=10)
        data = resp.json()
        # Etherscan V2 usually returns status "1" for normal endpoints, but for proxy it returns raw JSON-RPC
        if (
            resp.status_code == 200
            and "result" in data
            and data["result"].startswith("0x")
        ):
            logger.success("✅ PolygonScan: Successfully queried Etherscan V2 API.")
            return True
        else:
            logger.error(f"❌ PolygonScan: Query failed. Response: {data}")
            return False
    except Exception as e:
        logger.error(f"❌ PolygonScan: Request failed - {e}")
        return False


def check_polygon_rpc():
    rpc_url = os.getenv("POLYGON_RPC_URL")
    if not rpc_url:
        logger.error("❌ Polygon RPC: URL not set.")
        return False

    payload = {"jsonrpc": "2.0", "method": "eth_blockNumber", "params": [], "id": 1}
    try:
        resp = requests.post(rpc_url, json=payload, timeout=10)
        if resp.status_code == 200 and "result" in resp.json():
            logger.success(f"✅ Polygon RPC: Successfully queried {rpc_url}.")
            return True
        else:
            logger.error(
                f"❌ Polygon RPC: Query failed. HTTP {resp.status_code} - {resp.text}"
            )
            return False
    except Exception as e:
        logger.error(f"❌ Polygon RPC: Request failed - {e}")
        return False


def main():
    logger.info("Loading environment variables from .env...")
    # Load .env explicitly assuming this runs from the root or scripts/ folder
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    if not os.path.exists(env_path):
        env_path = os.path.join(os.path.dirname(__file__), ".env")

    if not os.path.exists(env_path):
        logger.error(
            "❌ Could not find .env file. Ensure it exists at the project root."
        )
        sys.exit(1)

    load_dotenv(env_path)

    logger.info("Testing external connections...")

    results = [
        check_motherduck(),
        check_discord(),
        check_polygonscan(),
        check_polygon_rpc(),
    ]

    if all(results):
        logger.success(
            "\n🎉 All environment configurations are valid and successfully connected!"
        )
        sys.exit(0)
    else:
        logger.warning(
            "\n⚠️ Some connections failed. Check the logs above and update your .env file."
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
