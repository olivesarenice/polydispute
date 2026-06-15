---
paths: ["**/*.py", "**/pyproject.toml", "**/Dockerfile*"]
description: "Python development conventions"
---

# Python Standards

## Language & Tooling
- **Python 3.12** strictly enforced — use modern syntax (type unions `X | None`, `match` statements)
- **uv** for all dependency management — never pip directly
- Core deps across all projects: `awswrangler`, `boto3`, `pandas`, `polars`, `loguru`

## Project Structure
```
project/
├── Dockerfile               # python:3.12-slim + uv
├── pyproject.toml           # uv format, references python-utils
├── src/ (not 100% strict, as long as the main components are present, you can have. multiple folders of this)
│   ├── main.py              # Entry point with argparse
│   ├── config.py            # Environment configuration
│   ├── backend/             # Processing modules
│   └── utils/               # Helper utilities
└── infra/                   # Terraform infrastructure if needed (AWS)
```


## Type Hints
All functions must have type hints. Use modern syntax:
```python
def process_data(items: list[dict], config: EnvSettings) -> dict[str, int]: ...
def get_user(user_id: str) -> User | None: ...
```

## Imports
Order: stdlib → third-party → local (absolute) → relative (same package).

## Logging
- **loguru only** — no `print()`, no stdlib `logging`
- Always include identifiers for traceability:
```python
from loguru import logger
logger.info(f"Processing run_id={run_id} batch={batch_num}/{total_batches}")
logger.info(f"Processed {success}/{total} records ({failed} failed)")
```
- Levels: `debug` (diagnostics), `info` (normal flow), `warning` (recoverable), `error` (failures), `success` (milestones)

## Entry Point Pattern
```python
import argparse
import sys
from loguru import logger

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pipeline description")
    parser.add_argument("--env", choices=["dev", "prod"], required=True)
    parser.add_argument("--t0", required=True, help="Start date (YYYY-MM-DD, inclusive)")
    parser.add_argument("--t1", required=True, help="End date (YYYY-MM-DD, exclusive)")
... and so on, add as needed 
    return parser.parse_args()

def main() -> int:
    args = parse_args()
    settings = get_settings(args.env)
    logger.info(f"Starting pipeline env={args.env} t0={args.t0} t1={args.t1}")
    try:
        result = run_pipeline(settings, args.t0, args.t1)
        logger.success(f"Completed: {result}")
        return 0
    except Exception as e:
        logger.exception(f"Pipeline failed: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
```

## Error Handling
- **Fail fast** for configuration: crash immediately on missing/invalid config at startup
- **Recover gracefully** during processing: log and continue, track success/failed counts

## Dockerfile Pattern
```dockerfile
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /app
COPY pyproject.toml uv.lock ./
ENV UV_SYSTEM_PYTHON=1 UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1
RUN --mount=type=cache,target=/root/.cache/uv \
    uv export --locked --no-dev -o requirements.txt \
    && uv pip install --system -r requirements.txt
COPY......
ENV PYTHONPATH=/app
ENTRY ,,.,,,
CMD ["--help"]
```
Dependencies before code for layer caching. Always `python:3.12-slim` base.

## Secrets Management
- **NEVER** commit `.env` files, credentials, API keys, or tokens.
- Use `.env.example` with placeholder values for documentation.
- **Production secrets**: AWS Secrets Manager or Parameter Store.
- **Local development**: `.env.<label>` files (gitignored).

```python
# NEVER hardcode
API_KEY = "sk-abc123..."

# CORRECT
API_KEY = os.getenv("API_KEY")
if not API_KEY:
    raise ValueError("API_KEY environment variable required")
```
