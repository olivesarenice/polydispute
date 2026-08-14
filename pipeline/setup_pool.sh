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

for POOL_NAME in "polydispute-local" "polydispute-dev"; do
    echo "Ensuring Prefect work pool '${POOL_NAME}' (type: docker) exists..."
    
    # Delete existing pool if it was created as type process previously
    $EXEC_PREFIX uv run prefect work-pool delete "$POOL_NAME" 2>/dev/null || true
    
    echo "Creating work pool '${POOL_NAME}' (type: docker)..."
    $EXEC_PREFIX uv run prefect work-pool create "$POOL_NAME" --type docker
    echo "✅ Work pool '${POOL_NAME}' created successfully!"
    echo ""
done
