# polydispute

Polydispute prediction market dispute analytics & resolution data pipeline. Ingests Discord dispute discussions, Polymarket market metadata, UMA Rocks committee signals, and CLOB 1-minute midpoint price histories into MotherDuck.

## Overview

The pipeline runs four sequential data operations via a unified CLI orchestrator:

1. **Phase 1: Discord Disputes** — Scrapes UMA `#disputes` threads/messages bounded by date range, ingesting raw data into MotherDuck and extracting `market_id` foreign keys to produce `clean_dc_threads`.
2. **Phase 2: Polymarket Catalog** — State-driven ingestion of Polymarket Gamma API metadata for active/disputed market IDs linked from Discord threads.
3. **Phase 3: UMA Rocks Signals** — State-driven incremental ingestion of UMA DVM committee consensus stances (`P1`-`P4`) from UMA Rocks API (`getPoolAnswers`).
4. **Phase 4: CLOB Price History** — High-resolution (1-min) midpoint price time-series pulled from Polymarket CLOB API for target disputed markets.

## Pipelines

### Phase 1: Discord (`1`)

Ingests QAC / UMA `#disputes` Discord thread starter posts and user discussion messages. The `load` operation bulk loads raw JSON payloads into `raw_dc_threads` / `raw_dc_messages` and automatically extracts `market_id` foreign keys into `clean_dc_threads`.

### Phase 2: Polymarket (`2`)

Queries `clean_dc_threads` joined with `raw_pm_markets` for non-settled market IDs to fetch metadata snapshots from Polymarket Gamma API.

### Phase 3: UMA Rocks (`3`)

Queries `MAX(timestamp)` in `raw_ur_signals` to perform incremental fetches of committee consensus stances (`P1`-`P4`) from UMA Rocks API.

### Phase 4: Price History (`4`)

Scans `clean_dc_threads` for active/unresolved markets and stages CLOB midpoint price history bars to `price_history.json` before loading into `raw_pm_price_history`.

## Project Structure

```
pipeline/
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

## CLI Arguments

| Arg | Required | Description |
|-----|----------|-------------|
| `--phase` | Yes | Phase number: `1` (Discord), `2` (Polymarket), `3` (UMA Rocks), `4` (Price History) |
| `--op` | No | Operation to run: `pull`, `load`, or `all` (default: `all`) |
| `--t0` | Yes (Phase 1 pull) | Start date (YYYY-MM-DD or ISO8601), midnight UTC |
| `--t1` | Yes (Phase 1 pull) | End date (YYYY-MM-DD or ISO8601), midnight UTC |
| `--limit` | No | Maximum market batch size for Phase 4 price history (default: 200) |
| `--no-retry` | No | Flag to disable retry logic on execution failure |

## Local Development

```bash
# Phase 1: Discord Disputes (Requires time window --t0 / --t1)
uv run python pipeline/src/run_pipelines.py --phase 1 --op all --t0 2026-08-07 --t1 2026-08-08

# Phase 2: Polymarket Catalog Metadata (State-driven)
uv run python pipeline/src/run_pipelines.py --phase 2 --op all

# Phase 3: UMA Rocks Committee Signals (State-driven)
uv run python pipeline/src/run_pipelines.py --phase 3 --op all

# Phase 4: CLOB Price History (State-driven)
uv run python pipeline/src/run_pipelines.py --phase 4 --op all
```