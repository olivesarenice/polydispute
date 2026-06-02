# Polydispute ELT Pipeline

This directory contains the robust ELT (Extract, Load, Transform) data pipeline for the Polydispute analytics engine. It is responsible for orchestrating the extraction of governance and dispute data across Polymarket, Discord, and the Polygon blockchain, and transforming it into a clean, relational dimensional model.

## 1. Pipeline Execution & Usage

The pipeline is split into Extraction (seeding raw data) and Transformation (cleaning and joining). 
**Note:** Always run extraction *before* transformation.

### Full Refresh (New Setup)
To perform a complete initialization from scratch:

```bash
# 1. Initialize the SQLite Database schema
uv run python pipeline/src/db_init.py

# 2. Extract Discord Threads & Messages (Example: All of May 2026)
uv run python pipeline/src/batch_seed.py --client discord --t0 2026-05-01 --t1 2026-05-31

# 3. Extract Polymarket Events & Markets (Must match the same timeframe)
uv run python pipeline/src/batch_seed.py --client polymarket --t0 2026-05-01 --t1 2026-05-31

# 4. Sweep Polygon Blockchain for UMA Resolution Rules
uv run python pipeline/src/pull_polygon.py --limit -1 --t0 2026-05-01 --t1 2026-05-31

# 5. Execute Transformation Layer (Transforms raw -> clean tables & builds analytical views)
uv run python pipeline/src/transform.py
```

### Incremental Updates
For daily or weekly updates, you only need to run the extraction for the delta period and then re-run the transformation layer.

```bash
# 1. Extract recent Discord data
uv run python pipeline/src/batch_seed.py --client discord --t0 2026-06-01 --t1 2026-06-07

# 2. Extract recent Polymarket data
uv run python pipeline/src/batch_seed.py --client polymarket --t0 2026-06-01 --t1 2026-06-07

# 3. Sweep Polygon for any newly discovered markets
uv run python pipeline/src/pull_polygon.py --limit 100 --t0 2026-06-01 --t1 2026-06-07

# 4. Rebuild the clean tables and views
uv run python pipeline/src/transform.py
```

## 2. Raw Data Model & Dependencies

The extraction layer pulls raw JSON payloads and loads them into an idempotent SQLite database without heavy modifications. The dependencies flow as follows:

*   **Polymarket Gamma API**
    *   `raw_pm_events` (1) -> (N) `raw_pm_markets`
    *   *Note:* The Polymarket API nests markets inside overarching "Events".
*   **Discord UMA Server**
    *   `raw_dc_threads` (1) -> (N) `raw_dc_messages`
    *   *Note:* Threads are created in the `#disputes` channel. Messages contain the community votes (P1-P4).
*   **Polygon RPC (UMA Oracle)**
    *   `raw_pm_markets` (1) -> (1) `raw_polygon_ancillary`
    *   *Note:* Uses the CTF Adapter address (`resolved_by`) and the `uma_question_id` (a bytes32 hash) to query the exact text of the resolution rules from the Polygon blockchain.

## 3. Transformation Layer (`transform.py`)

The transformation layer utilizes **Polars** to perform in-memory cleaning before loading the data into `clean_*` tables. We use a dimensional approach to keep the tables normalized, avoiding bloated, wide tables. 

### Key Extractions & Cleaning:
*   **`clean_dc_threads`**: 
    *   *Extraction:* Scans the raw message payloads for the string `market_id: \d+` (injected by the UMA bot).
    *   *Result:* Assigns a clean `market_id` to each thread so it can be joined natively to Polymarket data. Non-Polymarket threads missing this ID are safely kept but naturally ignored during downstream joins.
*   **`clean_dc_messages`**: 
    *   *Extraction:* Uses vectorized regex `(?i)\b(P[1-4])\b` to parse raw Discord content.
    *   *Result:* Extracts the exact vote type (`P1`, `P2`, `P3`, `P4`) and isolates it into a clean `vote_type` column. Unnecessary raw message text is dropped to save memory.
*   **`clean_pm_markets`**:
    *   *Standardization:* Maps the Gamma API's numeric ID to `market_id`, and the bytes32 oracle hash to `uma_question_id` to enforce strict ID hygiene. Propagates vital dispute signals like `uma_resolution_status`, `uma_bond`, and `neg_risk`.
*   **`clean_polygon_ancillary`**:
    *   *Standardization:* Enforces `uma_question_id` as the primary key. Retains the cleanly decoded UTF-8 resolution rules.

### The Analytical View (`disputes_view`)
Instead of duplicating joined data, the pipeline builds an SQLite `VIEW`. This aggregates the P1-P4 votes per thread and strictly joins the Discord, Polymarket, and Polygon domains using the cleansed IDs (`market_id` and `uma_question_id`). This serves as the single pane of glass for the dashboard backend.
