# Polydispute — System Architecture

Reflects the **actual build** (not the generic TECH_STACK.md template).
Single-container monolith: FastAPI serves both `/api/*` and the built React SPA.
One SQLite file is the whole datastore. A cron-driven Python pipeline writes to it.

```mermaid
flowchart TB
  user(["User browser"])

  subgraph ext["External services"]
    pm["Polymarket Gamma API<br/>(markets / events)"]
    poly["Polygon RPC — web3<br/>(UMA ancillary data)"]
    dc["Discord API<br/>(dispute threads / votes)"]
    sentry["Sentry<br/>(optional error tracking)"]
    r2[("Cloudflare R2<br/>whole-DB backup blob")]
  end

  subgraph vm["Hetzner VM — Coolify / Docker"]
    subgraph container["app container (single image)"]
      spa["React 19 SPA<br/>Vite build → frontend/dist<br/>Tailwind + recharts + axios"]
      api["FastAPI + Pydantic<br/>backend/src/app.py<br/>serves /api/* AND static SPA"]
    end

    cron["host cron"]

    subgraph pipe["pipeline (Python, cron-invoked)"]
      runner["run_pipelines.py /<br/>cron_runner.py"]
      conn["connectors:<br/>polymarket · polygon · discord"]
      transform["transform →<br/>clean_* tables + disputes_view"]
      wm["watermark files<br/>(on disk)"]
    end

    db[("SQLite<br/>pipeline/data/polydispute.db<br/>raw_* · clean_* · views")]
    backup["backup.sh (curl PUT)"]
  end

  %% request path
  user -->|HTTPS| api
  api -->|static html/js| user
  spa -.->|axios /api| api
  api -->|read| db
  api -.->|errors| sentry

  %% ingestion path
  cron --> runner
  cron --> backup
  runner --> conn
  runner <-->|read/advance| wm
  conn --> pm
  conn --> poly
  conn --> dc
  conn -->|raw JSON + raw_* upserts| db
  runner --> transform
  transform -->|write clean_* + views| db
  backup -->|PUT whole .db| r2

  %% template menu items intentionally not used for this app
  subgraph menu["TECH_STACK.md menu — not required by this app's design"]
    clerk["Clerk auth — not needed (no gated data)"]
    redis["Redis + TaskIQ — cron is sufficient"]
    vec["pgvector / vector search — no semantic search"]
    gem["GCP Gemini LLM — no LLM feature yet"]
  end

  classDef unused stroke-dasharray:5 5,fill:#f6f6f6,stroke:#999,color:#777;
  class clerk,redis,vec,gem unused;
  classDef risk fill:#fff3cd,stroke:#b8860b;
  class db risk;
```

## Notes

The template is a menu: components are pulled in only when a design requirement calls
for one. This app's requirements need none of Clerk / cloud DB / Redis+TaskIQ /
pgvector / Gemini, so their absence is intentional, not a gap.

Real items to watch (consequences of the chosen SQLite + cron + single-VM stack):

- **SQLite single-writer:** pipeline (writer) and API (reader) share one file. Set
  WAL mode + busy_timeout or reads will hit `database is locked` during a write.
- **Silent staleness:** the risky failure is the watermark quietly not advancing —
  Sentry won't catch it (nothing throws). Watch the `pipeline_runs` table.
- **Single file, single VM:** `backup.sh` PUTs the whole DB to R2 (good). Add
  retention/versioning and test `restore.sh` once.
