# Polydispute V3 Hybrid Calibration Plan

This plan details the end-to-end implementation for ingesting the UMA Rocks anchor (Tier 1) and calculating the historical accuracy of Discord users (Tier 2) to compute the final `Tau` edge in our data warehouse.

As requested, this isolates the work entirely within the pipeline layer. Backend API updates will be done later once the data is verified.

## Phase 1: Ingesting UMA Rocks (Tier 1 Anchor)

We will ingest the `getPoolAnswers` API to establish the baseline 22% anchor for the `Tau` engine.

**1. Create Connector (`pipeline/src/connectors/uma_rocks.py`)**
```python
import requests
from loguru import logger
from typing import List, Dict, Any

class UMARocksClient:
    API_URL = "https://www.uma.rocks/api/getPoolAnswers"
    
    def get_pool_answers(self) -> List[Dict[str, Any]]:
        logger.info(f"Fetching from {self.API_URL}")
        try:
            response = requests.get(self.API_URL, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to fetch UMA Rocks API: {e}")
            return []
```

**2. Update Schema (`pipeline/src/db_schema.py`)**
```python
TableConfig(
    name="raw_uma_rocks_signals",
    columns={
        "id": "TEXT PRIMARY KEY", # Synthetic ID or from the payload
        "question": "TEXT",
        "ancillaryData": "TEXT",
        "time": "INTEGER",
        "reward": "REAL",
        **get_dw_columns()
    }
)
```

**3. Pipeline Execution (`pipeline/src/pull_api.py`)**
- Add an ingestion flow in `pull_api.py` (during the `run_sync()` loop) to poll `UMARocksClient().get_pool_answers()` and dump JSON results into `raw_uma_rocks_signals`.

---

## Phase 2: Dynamic Voter Calibration (Tier 2 Social)

We will use a stateless SQLite `VIEW` to compute `discord_user_profiles` dynamically. 
To ease in new users and filter noise, we ignore uncalibrated users who haven't hit a `MIN_CALIBRATION_VOTES` threshold.

**1. Add Configuration (`pipeline/src/config.py`)**
```python
class PipelineConfig:
    # ... existing configs ...
    MIN_CALIBRATION_VOTES = 5  # Users with < 5 votes have 0 weight
```

**2. Transform Layer (`pipeline/src/transform.py`)**
We will add a new function `create_user_profiles_view()` right before `create_disputes_view()`.

```python
def create_user_profiles_view() -> None:
    logger.info("Creating discord_user_profiles view...")
    conn = get_sqlite_conn()
    
    view_sql = """
    CREATE VIEW discord_user_profiles AS
    SELECT 
        v.author_username,
        COUNT(v.message_id) AS total_predictions,
        SUM(
            CASE 
                -- P1 corresponds to YES (yes_price = 1.0)
                WHEN m.yes_price = 1.0 AND v.vote_type = 'P1' THEN 1
                -- P2 corresponds to NO (no_price = 1.0)
                WHEN m.no_price = 1.0 AND v.vote_type = 'P2' THEN 1
                ELSE 0
            END
        ) AS correct_predictions,
        CAST(SUM(
            CASE 
                WHEN m.yes_price = 1.0 AND v.vote_type = 'P1' THEN 1
                WHEN m.no_price = 1.0 AND v.vote_type = 'P2' THEN 1
                ELSE 0
            END
        ) AS REAL) / COUNT(v.message_id) AS lifetime_accuracy
    FROM clean_dc_messages v
    JOIN clean_dc_threads t ON v.thread_id = t.thread_id
    JOIN clean_pm_markets m ON t.market_id = m.market_id
    WHERE m.uma_resolution_status = 'resolved'
    GROUP BY v.author_username;
    """
    
    conn.execute("DROP VIEW IF EXISTS discord_user_profiles")
    conn.execute(view_sql)
    conn.commit()
    conn.close()
```

---

## Phase 3: The Tau Engine (`disputes_view`)

We rewrite `create_disputes_view()` to calculate `weighted_p1` and `weighted_p2`. We apply the rule: if `total_predictions` < `MIN_CALIBRATION_VOTES`, their weight is `0.0`.

```python
from config import PipelineConfig

def create_disputes_view() -> None:
    conn = get_sqlite_conn()
    
    # We join clean_dc_messages against discord_user_profiles
    # and sum their lifetime_accuracy if they pass the threshold.
    view_sql = f"""
    CREATE VIEW disputes_view AS
    SELECT 
        t.thread_id,
        m.condition_id,
        m.question,
        m.slug,
        m.uma_resolution_status,
        m.uma_bond,
        m.uma_reward,
        m.neg_risk,
        m.yes_price,
        m.no_price,
        
        -- Raw counts
        COUNT(CASE WHEN v.vote_type = 'P1' THEN 1 END) AS p1_votes,
        COUNT(CASE WHEN v.vote_type = 'P2' THEN 1 END) AS p2_votes,
        
        -- Weighted scores (Tier 2 Math)
        SUM(
            CASE 
                WHEN v.vote_type = 'P1' AND COALESCE(u.total_predictions, 0) >= {PipelineConfig.MIN_CALIBRATION_VOTES} 
                THEN u.lifetime_accuracy 
                ELSE 0 
            END
        ) AS weighted_p1_votes,
        SUM(
            CASE 
                WHEN v.vote_type = 'P2' AND COALESCE(u.total_predictions, 0) >= {PipelineConfig.MIN_CALIBRATION_VOTES} 
                THEN u.lifetime_accuracy 
                ELSE 0 
            END
        ) AS weighted_p2_votes,
        
        p.ancillary_data_decoded
    FROM clean_dc_threads t
    JOIN clean_pm_markets m ON t.market_id = m.market_id
    LEFT JOIN clean_dc_messages v ON t.thread_id = v.thread_id
    LEFT JOIN discord_user_profiles u ON v.author_username = u.author_username
    LEFT JOIN clean_polygon_ancillary p ON m.uma_question_id = p.uma_question_id
    GROUP BY t.thread_id;
    """
    
    conn.execute("DROP VIEW IF EXISTS disputes_view")
    conn.execute(view_sql)
    conn.commit()
    conn.close()
```

## Phase 4: Backend Integration (Deferred)

Once the pipeline generates correct data, we will:
1. Fuzzy-match `uma_rocks_signals.question` with `clean_pm_markets.question` to lock in the 22% Tier 1 anchor.
2. Calculate the final `Tau` mathematically in `app.py`.
3. Feed the Discord X-Ray dashboard via the API.
