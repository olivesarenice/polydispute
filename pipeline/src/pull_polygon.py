import argparse
import sys
from typing import List

from loguru import logger

from config import PolygonConfig
from connectors.polygon import PolygonClient
from db_utils import get_sqlite_conn, load_json_to_table
from dotenv import load_dotenv

load_dotenv()


def run_polygon_sync(limit: int = 500, t0_str: str = None, t1_str: str = None) -> None:
    """
    Sweeps raw_pm_markets for missing ancillaryData and queries Polygon directly.
    Prioritizes newer markets using ORDER BY end_date DESC.
    """
    conn = get_sqlite_conn()
    cursor = conn.cursor()

    # Self-heal: purge any records where ancillaryData was empty (b'') due to hitting wrong adapter previously
    cursor.execute("DELETE FROM raw_polygon_ancillary WHERE ancillary_data_decoded = '' OR ancillary_data_decoded IS NULL")
    conn.commit()

    query = """
        SELECT DISTINCT pm.uma_question_id, pm.resolved_by 
        FROM raw_pm_markets pm
        LEFT JOIN raw_polygon_ancillary poly ON pm.uma_question_id = poly.question_id
        WHERE poly.question_id IS NULL AND pm.uma_question_id IS NOT NULL
    """
    
    params = ()
    
    if t0_str:
        if "T" not in t0_str:
            t0_str += "T00:00:00Z"
        query += " AND pm.start_date >= ?"
        params += (t0_str,)
        
    if t1_str:
        if "T" not in t1_str:
            t1_str += "T00:00:00Z"
        query += " AND pm.start_date < ?"
        params += (t1_str,)

    query += " ORDER BY pm.end_date DESC"

    if limit > 0:
        query += f" LIMIT {limit}"

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    markets = [(row[0], row[1]) for row in rows]

    if not markets:
        logger.info("No missing Polygon ancillary data found. DB is fully synced.")
        return

    logger.info(
        f"Found {len(markets)} missing ancillary records. Querying Polygon RPC..."
    )

    client = PolygonClient()

    # Process in chunks of 100 to manage memory
    chunk_size = 100
    for i in range(0, len(markets), chunk_size):
        chunk = markets[i : i + chunk_size]
        raw_records = []

        for q_id, resolved_by in chunk:
            adapter_address = resolved_by if resolved_by else PolygonConfig.DEFAULT_CTF_ADAPTER
            try:
                uma_data = client.get_uma_question(adapter_address, q_id)
                raw_records.append(uma_data.model_dump(by_alias=False))
            except Exception as e:
                logger.warning(f"Failed to fetch on-chain data for {q_id} using adapter {adapter_address}: {e}")

        if raw_records:
            logger.info(
                f"Loading {len(raw_records)} ancillary records into raw_polygon_ancillary..."
            )
            load_json_to_table("raw_polygon_ancillary", raw_records, pk="question_id")
        else:
            logger.warning(f"No records fetched in chunk {i//chunk_size}.")


def main() -> int:
    parser = argparse.ArgumentParser(description="ELT Polygon Sweeper")
    parser.add_argument(
        "--limit",
        type=int,
        default=500,
        help="Max number of on-chain queries per run. Use -1 to run for everything.",
    )
    parser.add_argument("--t0", type=str, required=False, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--t1", type=str, required=False, help="End date (YYYY-MM-DD)")
    args = parser.parse_args()

    try:
        run_polygon_sync(limit=args.limit, t0_str=args.t0, t1_str=args.t1)
        return 0
    except Exception as e:
        logger.exception(f"Polygon sweeper failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
