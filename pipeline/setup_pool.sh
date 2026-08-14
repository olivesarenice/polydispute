#!/usr/bin/env bash
set -e

POOL_NAME="polydispute-local"
POOL_TYPE="process"

# Use Doppler if available/configured, otherwise fallback to src/.env
if command -v doppler &> /dev/null && (doppler secrets &> /dev/null || [ -n "$DOPPLER_TOKEN" ]); then
    echo "🔑 Using Doppler for secrets management..."
    EXEC_PREFIX="doppler run --"
elif [ -f "src/.env" ]; then
    echo "📄 Loading environment variables from src/.env..."
    set -a
    source src/.env
    set +a
    EXEC_PREFIX=""
else
    echo "⚠️ Warning: Neither Doppler nor src/.env found. Ensure environment variables are exported."
    EXEC_PREFIX=""
fi

# 1. Local Pool: Type docker (spins up local docker containers via OrbStack on Mac)
echo "Ensuring Prefect work pool 'polydispute-local' (type: docker) exists..."
$EXEC_PREFIX uv run prefect work-pool delete "polydispute-local" 2>/dev/null || true
$EXEC_PREFIX uv run prefect work-pool create "polydispute-local" --type docker
echo "✅ Work pool 'polydispute-local' (type: docker) ready!"
echo ""

# 2. Remote Dev Pool: Type process (executes directly inside the Coolify container)
echo "Ensuring Prefect work pool 'polydispute-dev' (type: process) exists..."
$EXEC_PREFIX uv run prefect work-pool delete "polydispute-dev" 2>/dev/null || true
$EXEC_PREFIX uv run prefect work-pool create "polydispute-dev" --type process
echo "✅ Work pool 'polydispute-dev' (type: process) ready!"
echo ""
