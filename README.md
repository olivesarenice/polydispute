# Polydispute Web Application & Analytical Engine

This repository contains the unified web application and analytical backend for the Polydispute prediction market dispute resolution engine. It combines a high-performance **FastAPI** analytical API querying **MotherDuck** with a modern **React 18** Single-Page Application (SPA) designed to surface governance edge, voter credibility calibration, and dispute outcome projections.

---

## 1. Developer Onboarding & Configuration Setup

### Configuration Architecture
- **Secrets Management**: Environment variables and credentials are centrally managed in **Doppler** (`polydispute` project). Secrets are never committed to Git or stored in static plaintext `.env` files.
- **Local Dev Sync**: Uses `direnv` combined with `doppler` CLI. When working locally, secrets are injected dynamically into RAM at runtime via `doppler run --`.
- **Production Containerization**: Deployed on Hetzner via **Coolify** using Docker Compose. Container execution is wrapped at boot via `ENTRYPOINT ["doppler", "run", "--"]` matching the pipeline worker pattern.

### First-Time Dev Setup CLI Steps

```bash
# 1. Install required CLI tooling via Homebrew
brew install uv node dopplerhq/cli/doppler direnv

# 2. Authenticate with Doppler and link project configuration
doppler login
doppler setup --project polydispute --config dev

# 3. Install Python backend and Node frontend dependencies
uv sync
cd frontend && npm install && cd ..

# 4. Launch development services (in separate terminals)

# Terminal A: FastAPI Analytical Backend (Port 8000 with auto-reload)
doppler run -- uvicorn backend.src.app:app --host 0.0.0.0 --port 8000 --reload

# Terminal B: React 18 / Vite Development Server (Port 5173 with HMR)
cd frontend && npm run dev
```

---

## 2. Application Architecture & Serving Layout

The production build runs as a **single-container monolith**: FastAPI serves all `/api/*` data routes and directly delivers the compiled React production bundle (`frontend/dist`) for root and SPA client-side routes without requiring a separate Node.js server or Nginx container.

```
polydispute/
├── Dockerfile                  # Multi-stage: Node 20 builder -> Python 3.12 runtime (~220 MB)
├── docker-compose.yml          # Coolify service specification (Port 8000, Doppler injection)
├── pyproject.toml              # Lean web runtime dependencies (duckdb, fastapi, sentry-sdk, etc.)
├── uv.lock                     # Deterministic dependency lockfile
├── backend/                    # Python FastAPI analytical engine
│   └── src/
│       ├── app.py              # API routes, Sentry APM tracing, SPA static mount
│       ├── config.py           # Pydantic Settings & MotherDuck database resolution
│       ├── db.py               # Thread-safe MotherDuck connection pool & healthchecks
│       ├── analytics.py        # Empirical Bayes voter calibration & quadratic consensus models
│       └── schemas.py          # Strict Pydantic response validation models
└── frontend/                   # React 18 / Tailwind CSS client application
    ├── src/
    │   ├── App.jsx             # Top-level state controller & telemetry status gate
    │   ├── components/         # Modular dashboard panels (Screener, Replay, Logos)
    │   ├── lib/api.js          # Resilient MotherDuck API client with retry logic
    │   └── index.css           # Curated dark-mode design system
    ├── public/                 # Static vector assets & Scales of Themis favicon.svg
    └── dist/                   # Compiled production bundle output from Vite
```

---

## 3. Containerization & Coolify Deployment

### Multi-Stage Build Pipeline
1. **Stage 1 (`frontend-builder`)**: Uses `node:20-alpine` to execute `npm ci` and `npm run build`, outputting minified static assets to `/build/dist`.
2. **Stage 2 (`runtime`)**: Uses `python:3.12-slim`, installs `doppler` CLI and `curl`, runs `uv sync --frozen --no-dev` using BuildKit caching, and copies `frontend/dist` into the web root.

### Docker Compose Orchestration
The application is declared in [`docker-compose.yml`](docker-compose.yml) and deployed via Coolify:

```yaml
services:
  polydispute:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: polydispute-app
    restart: unless-stopped
    ports:
      - "8000:8000"
    environment:
      - DOPPLER_TOKEN=${DOPPLER_TOKEN}
      - DOPPLER_CONFIG=${DOPPLER_CONFIG:-prd}
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/health"]
      interval: 20s
      timeout: 5s
      retries: 3
      start_period: 15s
```

### Coolify Quick Deploy Steps
1. Navigate to your Coolify dashboard $\rightarrow$ **+ New Resource** $\rightarrow$ **Git Repository**.
2. Set **Build Pack** to `Docker Compose` and specify `/docker-compose.yml`.
3. In **Environment Variables** (or Shared Project Variables), set `DOPPLER_TOKEN`.
4. Bind your public domain (e.g. `https://polydispute.yourdomain.com`). Traefik routes public HTTPS directly to container port `8000`.
5. Click **Deploy**.

---

## 4. Core Analytical Models & API Endpoints

### Empirical Bayes Voter Scoring
The analytical engine scores community forecasters using an Empirical Bayes shrinkage model to mitigate small-sample noise:

$$S_u = \frac{R_u + N \cdot P}{G_u + N}$$

- $R_u$: Lifetime correct consensus predictions
- $G_u$: Lifetime participated dispute votes
- $N$: Prior pseudo-votes trust parameter (default: 20)
- $P$: Prior baseline accuracy (default: 50.0%)

Consensus projection applies quadratic power weighting ($W_u = S_u^2$) to map forecaster signals ($P1=\$0.00, P2=\$1.00, P3=\$0.50, P4=P(t)$) into point-in-time expected resolution prices.

### API Reference

| Endpoint | Method | Description | Cache TTL |
|---|---|---|---|
| `/api/health` | `GET` | MotherDuck connectivity ping, query latency (ms), and memory cache status | None (Live) |
| `/api/markets` | `GET` | Filterable screener catalog of disputed prediction markets with consensus metrics | 60s |
| `/api/markets/{id}/detail` | `GET` | Deep-dive analytics, 1-min CLOB price trajectory, voter breakdown, consensus replay | 30s |
| `/api/leaderboard` | `GET` | Forecaster rankings, Bayesian accuracy scores, and lifetime accuracy statistics | 120s |
| `/api/pipeline/status` | `GET` | Pipeline synchronization watermarks and fresh database timestamps | 60s |

### Observability & APM Tracing
- **Sentry APM**: Automatic transaction tracing for all API routes (`traces_sample_rate=1.0`).
- **Proxy Client IP Resolution**: Inspects `CF-Connecting-IP`, `X-Forwarded-For`, and `X-Real-IP` to extract real origin IPs behind Coolify / Traefik.
- **Microsecond Latency Headers**: Injects `X-Process-Time: {ms}` into all HTTP responses.