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

if [ ! -f "$DB_PATH" ]; then
    echo "Error: Database file $DB_PATH not found."
    exit 1
fi

# Parse R2_ENDPOINT: https://<ACCOUNT_ID>.r2.cloudflarestorage.com/<BUCKET>/<PREFIX>
NO_PROTO="${R2_ENDPOINT#https://}"
ACCOUNT_ID="${NO_PROTO%%.r2*}"
REST="${NO_PROTO#*/}"
BUCKET="${REST%%/*}"
PREFIX="${REST#*/}"

FILE_NAME="polydispute.db"
FULL_KEY="${PREFIX}/${FILE_NAME}"

API_URL="https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/r2/buckets/${BUCKET}/objects/${FULL_KEY}"

echo "Backing up $DB_PATH to R2 (Bucket: $BUCKET, Path: $FULL_KEY)..."

HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X PUT "$API_URL" \
  -H "Authorization: Bearer ${R2_API_TOKEN}" \
  -H "Content-Type: application/octet-stream" \
  --data-binary "@${DB_PATH}")

if [ "$HTTP_STATUS" -eq 200 ] || [ "$HTTP_STATUS" -eq 201 ]; then
    echo "Backup successful!"
else
    echo "Backup failed with HTTP status $HTTP_STATUS."
    # Print the error body for debugging
    curl -s -X PUT "$API_URL" \
      -H "Authorization: Bearer ${R2_API_TOKEN}" \
      -H "Content-Type: application/octet-stream" \
      --data-binary "@${DB_PATH}"
    exit 1
fi
