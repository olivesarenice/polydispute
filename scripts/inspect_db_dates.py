import sys
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PIPELINE_SRC = PROJECT_ROOT / "pipeline" / "src"
if str(PIPELINE_SRC) not in sys.path:
    sys.path.insert(0, str(PIPELINE_SRC))

load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(PIPELINE_SRC / ".env")

from db_utils import get_db_conn

def check():
    conn = get_db_conn()
    print("=== MOTHERDUCK DATABASE AUDIT ===")
    
    tables = [r[0] for r in conn.execute("SHOW TABLES").fetchall()]
    print(f"Tables in DB: {tables}\n")
    
    date_queries = {
        "raw_pm_markets": "SELECT MAX(end_date), MAX(closed_time), MAX(_created_at) FROM raw_pm_markets",
        "raw_dc_threads": "SELECT MAX(timestamp), MAX(_created_at) FROM raw_dc_threads",
        "raw_dc_messages": "SELECT MAX(timestamp), MAX(_created_at) FROM raw_dc_messages",
        "clean_pm_markets": "SELECT MAX(closed_time), MAX(uma_end_date) FROM clean_pm_markets",
        "clean_dc_threads": "SELECT MAX(timestamp) FROM clean_dc_threads",
        "pipeline_runs": "SELECT MAX(start_time), MAX(end_time) FROM pipeline_runs",
    }
    
    for tbl, q in date_queries.items():
        if tbl in tables:
            try:
                res = conn.execute(q).fetchone()
                print(f"{tbl:22}: {res}")
            except Exception as e:
                print(f"{tbl:22}: Error executing ({e})")
        else:
            print(f"{tbl:22}: Table not found")

    conn.close()

if __name__ == "__main__":
    check()
