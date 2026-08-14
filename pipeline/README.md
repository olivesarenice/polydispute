# Polydispute ELT Pipeline

This directory contains the modular ELT (Extract, Load, Transform) data pipeline for the Polydispute prediction market analytics engine. It orchestrates the ingestion of Discord dispute discussions, Polymarket market metadata, UMA Rocks committee voting signals, and 1-minute CLOB price histories into MotherDuck.

---

## 1. Developer Onboarding & Configuration Setup

### Configuration Architecture
- **Secrets Management**: Environment variables and secrets are centrally managed in **Doppler** (`polydispute` project). Secrets are never committed to Git or stored in static plaintext `.env` files.
- **Local Dev Ingestion**: Uses `direnv` combined with `doppler` CLI. When you `cd` into `pipeline/`, secrets are dynamically injected into your shell's RAM.
- **Production Workers**: Containerized in Coolify on Hetzner via `Dockerfile.worker`. Wrapped at container boot via `ENTRYPOINT ["doppler", "run", "--"]`.

### First-Time Dev Setup CLI Steps

```bash
# 1. Install required CLI dependencies via Homebrew
brew install uv dopplerhq/cli/doppler direnv

# 2. Hook direnv into your shell (add to ~/.zshrc if not already present)
echo 'eval "$(direnv hook zsh)"' >> ~/.zshrc && source ~/.zshrc

# 3. Authenticate with Doppler and link the project config
doppler login
cd pipeline
doppler setup --project polydispute --config dev

# 4. Create local .envrc for automatic direnv + doppler syncing
echo 'eval "$(doppler secrets download --no-file --format env)"' > .envrc
direnv allow

# 5. Provision the local Prefect work pool and start worker
./setup_pool.sh

# 6. Register pipeline deployments to the Prefect server
uv run python src/deploy.py
```

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
