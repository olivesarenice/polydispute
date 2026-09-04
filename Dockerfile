# ─── STAGE 1: FRONTEND ASSET COMPILATION ───
FROM node:20-alpine AS frontend-builder
WORKDIR /build

# Copy frontend package manifests for layer caching
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci

# Copy frontend source code and compile production bundle
COPY frontend/ ./
RUN npm run build

# ─── STAGE 2: PYTHON BACKEND & WEB RUNTIME (Coolify / Docker) ───
FROM python:3.12-slim
WORKDIR /app

# Target Doppler Project & Config (matching pipeline worker)
ENV DOPPLER_PROJECT=polydispute
ENV DOPPLER_CONFIG=prd

# Enable bytecode compilation, copy link mode, and configure paths
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app"

# 1. Install Doppler CLI, curl (for Coolify healthchecks), and certificates
RUN apt-get update && apt-get install -y --no-install-recommends \
    apt-transport-https \
    ca-certificates \
    curl \
    gnupg \
    && mkdir -p /etc/apt/keyrings \
    && curl -sLf --retry 3 --tlsv1.2 --proto "=https" 'https://packages.doppler.com/public/cli/gpg.DE2A7741A397C129.key' | gpg --dearmor -o /etc/apt/keyrings/doppler.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/doppler.gpg] https://packages.doppler.com/public/cli/deb/debian any-version main" | tee /etc/apt/sources.list.d/doppler-cli.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends doppler \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 2. Copy uv binary from official Astral image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# 3. Copy dependency manifests for layer caching
COPY pyproject.toml uv.lock ./

# 4. Install dependencies into /app/.venv using BuildKit cache mount
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# 5. Copy compiled frontend assets from Stage 1 into web root
COPY --from=frontend-builder /build/dist ./frontend/dist

# 6. Copy backend application source
COPY backend/ ./backend/

EXPOSE 8000

# 1:1 parity with pipeline/Dockerfile.worker: wrap all container execution with Doppler
ENTRYPOINT ["doppler", "run", "--"]
CMD ["uvicorn", "backend.src.app:app", "--host", "0.0.0.0", "--port", "8000"]
