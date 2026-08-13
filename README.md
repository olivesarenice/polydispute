# polydispute

Polydispute prediction market dispute analytics & resolution data pipeline. Ingests Discord dispute discussions, Polymarket market metadata, UMA Rocks committee signals, and CLOB 1-minute midpoint price histories into MotherDuck.

---

## Overview

The pipeline runs four sequential data operations via a unified CLI orchestrator:

1. **Phase 1: Discord Disputes** — Scrapes UMA `#disputes` threads/messages bounded strictly by UTC 00:00 calendar date range (or rolling last 24h), ingesting raw data into MotherDuck and extracting 6-8 digit `market_id` foreign keys to produce `clean_dc_threads`.
2. **Phase 2: Polymarket Catalog** — State-driven ingestion of Polymarket Gamma API metadata for active/disputed market IDs linked from Discord threads.
3. **Phase 3: UMA Rocks Signals** — State-driven incremental ingestion of UMA DVM committee consensus stances (`P1`-`P4`) from UMA Rocks API (`getPoolAnswers`).
4. **Phase 4: CLOB Price History** — High-resolution (1-min) midpoint price time-series pulled in parallel from Polymarket CLOB API and staged as ZSTD Parquet.

---

## Incremental Pipeline Execution

Run the complete pipeline sequence for daily/weekly incremental updates:

```bash
# 1. Phase 1: Discord Disputes
# Mode A (Auto-Range): Rolling last 24 hours (-1 day) from current execution time if --t0/--t1 omitted
uv run python pipeline/src/run_pipelines.py --phase 1 --op all

# Mode B (Explicit Date Range): Strict 00:00 UTC calendar date bounds (e.g., 2026-08-12T00:00:00Z -> 2026-08-13T00:00:00Z)
uv run python pipeline/src/run_pipelines.py --phase 1 --op all --t0 2026-08-12 --t1 2026-08-13

# 2. Phase 2: Polymarket Catalog Metadata (State-driven)
uv run python pipeline/src/run_pipelines.py --phase 2 --op all

# 3. Phase 3: UMA Rocks Committee Signals (State-driven)
uv run python pipeline/src/run_pipelines.py --phase 3 --op all

# 4. Phase 4: CLOB Price History (State-driven, 16 parallel threads)
uv run python pipeline/src/run_pipelines.py --phase 4 --op all --targets unresolved --threads 16
```

---

## Project Structure

```
pipeline/
├── data/
│   └── raw/                      # Stage-isolated raw data outputs
│       ├── discord/              # output_<unix>.json
│       ├── polymarket/           # output_<unix>.json
│       ├── umarocks/             # output_<unix>.json
│       └── price_history/        # output_<unix>.parquet
└── src/
    ├── run_pipelines.py          # Unified CLI orchestrator
    ├── db_schema.py              # MotherDuck database table definitions
    ├── db_utils.py               # Database connections & bulk load utilities
    ├── db_init.py                # Schema initialization script
    ├── config.py                 # Environment configuration
    ├── connectors/               # API clients (Discord, Polymarket, UMA Rocks)
    ├── pipes/                    # Pipe modules (Phase 1-4 pull/load scripts)
    │   ├── discord/              # pull.py, load.py
    │   ├── polymarket/           # pull.py, load.py
    │   ├── umarocks/             # pull.py, load.py
    │   └── price_history/        # pull.py, load.py
    └── utils/                    # Shared time utilities
```

---

## CLI Options

| Arg | Required | Description |
|-----|----------|-------------|
| `--phase` | Yes | Phase number: `1` (Discord), `2` (Polymarket), `3` (UMA Rocks), `4` (Price History) |
| `--op` | No | Operation to run: `pull`, `load`, or `all` (default: `all`) |
| `--t0` | Optional | Start date (YYYY-MM-DD parses to 00:00 UTC); defaults to rolling 24h ago if omitted |
| `--t1` | Optional | End date (YYYY-MM-DD parses to 00:00 UTC); defaults to now UTC if omitted |
| `--limit` | No | Maximum market batch size for Phase 4 price history (default: None, unlimited) |
| `--targets` | No | Target filter: `unresolved` (default) or `all` (full backfill) |
| `--fidelity` | No | CLOB price history sampling resolution in minutes (default: `1`) |
| `--threads` | No | Number of parallel worker threads for price history pulling (default: `8`) |