# Polydispute ELT Pipeline

This directory contains the modular ELT (Extract, Load, Transform) data pipeline for the Polydispute prediction market analytics engine. It orchestrates the ingestion of Discord dispute discussions, Polymarket market metadata, UMA Rocks committee voting signals, and 1-minute CLOB price histories into MotherDuck.

---

## 1. Incremental Pipeline Execution

Run the four sequential phases in order for routine incremental pipeline execution:

```bash
# Step 1: Discord Disputes
# Mode A (Auto-Range): Defaults to rolling 24 hours (-1 day) from current execution time if --t0/--t1 omitted
uv run python pipeline/src/run_pipelines.py --phase 1 --op all

# Mode B (Explicit Date Range): Bounds strictly to 00:00 UTC calendar dates (e.g., 2026-08-12T00:00:00Z -> 2026-08-13T00:00:00Z)
uv run python pipeline/src/run_pipelines.py --phase 1 --op all --t0 2026-08-12 --t1 2026-08-13

# Step 2: Polymarket Metadata (State-driven: fetches Gamma metadata for active/new market IDs)
uv run python pipeline/src/run_pipelines.py --phase 2 --op all

# Step 3: UMA Rocks Signals (State-driven: incrementally pulls committee consensus since MAX(timestamp))
uv run python pipeline/src/run_pipelines.py --phase 3 --op all

# Step 4: CLOB Price History (State-driven: pulls 1-min midpoint bars since MAX(observed_at))
uv run python pipeline/src/run_pipelines.py --phase 4 --op all --targets unresolved --threads 16
```

---

## 2. Phase Architecture & Staging Layout

Each phase operates under a two-stage pattern (**Pull** $\to$ **Load**):
- **Pull**: Fetches raw data from external APIs and saves stage-isolated payloads to `pipeline/data/raw/<stage_name>/output_<unix>.<ext>`.
- **Load**: Ingests staged files into MotherDuck `raw_*` tables and executes Silver `clean_*` transformations.

### Raw Data Staging Structure
```
pipeline/data/raw/
├── discord/          # output_<unix>.json (Discord threads & discussion messages)
├── polymarket/       # output_<unix>.json (Polymarket Gamma API market metadata)
├── umarocks/         # output_<unix>.json (UMA Rocks committee consensus signals)
└── price_history/    # output_<unix>.parquet (ZSTD-compressed 1-min CLOB midpoint bars)
```

---

## 3. Data Transformation & Validation Rules

- **`clean_dc_threads`**: Scans Discord starter posts and discussion messages for Polymarket URLs and `market_id: \d+` tags, extracting valid 6-to-8 digit `market_id` foreign keys (`6 <= len(market_id) <= 8`).
- **`clean_dc_messages`**: Parses community voting stances (`P1`, `P2`, `P3`, `P4`) from raw Discord message bodies using vectorized regex matching.
- **`clean_pm_markets`**: Normalizes outcome prices (`yes_price`, `no_price`), parses outcome token array IDs (`clob_token_ids`), and casts dates to native `TIMESTAMPTZ`.
- **`clean_ur_signals`**: Formats UMA Rocks DVM committee answers (`P1`–`P4`) and computes `timestamp_iso` (`TIMESTAMPTZ`).
