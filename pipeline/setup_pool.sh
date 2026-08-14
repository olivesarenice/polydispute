#!/usr/bin/env bash
set -e

POOL_NAME="polydispute-pool"
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

echo "Ensuring Prefect work pool '${POOL_NAME}' exists..."

# Check if pool exists (suppress output)
if $EXEC_PREFIX uv run prefect work-pool inspect "$POOL_NAME" > /dev/null 2>&1; then
    echo "✅ Work pool '${POOL_NAME}' already exists."
else
    echo "Creating work pool '${POOL_NAME}' (type: ${POOL_TYPE})..."
    $EXEC_PREFIX uv run prefect work-pool create "$POOL_NAME" --type "$POOL_TYPE"
    echo "✅ Work pool '${POOL_NAME}' created successfully!"
fi

echo ""
echo "🚀 Starting local Prefect worker for '${POOL_NAME}' (Press Ctrl+C to stop)..."
$EXEC_PREFIX uv run prefect worker start --pool "$POOL_NAME"
