#!/usr/bin/env bash
set -e

# Change to the root of the project
cd "$(dirname "$0")/.."

# Source the environment file if it exists
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Ensure R2 config is defined
if [ -z "$R2_ENDPOINT" ] || [ -z "$R2_API_TOKEN" ]; then
    echo "Error: R2_ENDPOINT or R2_API_TOKEN is not set in .env"
    exit 1
fi

DB_PATH="pipeline/data/polydispute.db"

# Parse R2_ENDPOINT: https://<ACCOUNT_ID>.r2.cloudflarestorage.com/<BUCKET>/<PREFIX>
NO_PROTO="${R2_ENDPOINT#https://}"
ACCOUNT_ID="${NO_PROTO%%.r2*}"
REST="${NO_PROTO#*/}"
BUCKET="${REST%%/*}"
PREFIX="${REST#*/}"

FILE_NAME="polydispute.db"
FULL_KEY="${PREFIX}/${FILE_NAME}"

API_URL="https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/r2/buckets/${BUCKET}/objects/${FULL_KEY}"

# Create the data directory if it doesn't exist
mkdir -p pipeline/data

echo "Restoring from R2 (Bucket: $BUCKET, Path: $FULL_KEY) to $DB_PATH..."

HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X GET "$API_URL" \
  -H "Authorization: Bearer ${R2_API_TOKEN}")

if [ "$HTTP_STATUS" -eq 200 ]; then
    curl -s -X GET "$API_URL" \
      -H "Authorization: Bearer ${R2_API_TOKEN}" \
      -o "$DB_PATH"
    echo "Restore successful!"
else
    echo "Restore failed with HTTP status $HTTP_STATUS."
    # Print the error body for debugging
    curl -s -X GET "$API_URL" \
      -H "Authorization: Bearer ${R2_API_TOKEN}"
    exit 1
fi
