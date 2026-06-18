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
META_NAME="polydispute.db.meta.json"
FULL_KEY="${PREFIX}/${FILE_NAME}"
META_KEY="${PREFIX}/${META_NAME}"

API_URL="https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/r2/buckets/${BUCKET}/objects/${FULL_KEY}"
META_URL="https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/r2/buckets/${BUCKET}/objects/${META_KEY}"

# Create the data directory if it doesn't exist
mkdir -p pipeline/data

# Require an explicit "yes" before performing a destructive action
confirm() {
    local reply
    printf 'Type [yes] to confirm: '
    read -r reply
    if [ "$reply" != "yes" ]; then
        echo "Aborted."
        exit 1
    fi
}

# Build a metadata JSON for the db blob: { sha256, last_modified, size_mb }
db_meta_json() {
    local f="$1"
    local hash size_bytes size_mb last_modified
    hash=$(sha256sum "$f" | awk '{print $1}')
    # Data size = file size minus free (deleted) pages, computed read-only.
    # This reflects deletes without rewriting the file, so the hash stays stable.
    size_bytes=$(sqlite3 "$f" "SELECT (page_count - freelist_count) * page_size FROM pragma_page_count(), pragma_freelist_count(), pragma_page_size();")
    size_mb=$(awk "BEGIN{printf \"%.2f\", ${size_bytes}/1024/1024}")
    last_modified=$(date -u -d "@$(stat -c '%Y' "$f")" +"%Y-%m-%d %H:%M:%S")
    jq -n --arg sha "$hash" --arg lm "$last_modified" --argjson smb "$size_mb" \
        '{sha256:$sha, last_modified:$lm, size_mb:$smb}'
}

# Fetch the remote metadata (if any) to compare snapshots before overwriting local
TMP_META=$(mktemp)
trap 'rm -f "$TMP_META"' EXIT
REMOTE_STATUS=$(curl -s -o "$TMP_META" -w "%{http_code}" -X GET "$META_URL" \
  -H "Authorization: Bearer ${R2_API_TOKEN}")

if [ "$REMOTE_STATUS" -eq 200 ] && jq -e . "$TMP_META" >/dev/null 2>&1; then
    REMOTE_SHA=$(jq -r '.sha256 // ""' "$TMP_META")
    if [ -f "$DB_PATH" ]; then
        LOCAL_META=$(db_meta_json "$DB_PATH")
        LOCAL_SHA=$(echo "$LOCAL_META" | jq -r '.sha256')
        if [ "$REMOTE_SHA" = "$LOCAL_SHA" ]; then
            echo "No change in DB, skip."
            exit 0
        fi
        # DB differs: show what restoring will overwrite locally (r2 --> local)
        echo "DB differs — restoring will overwrite local (r2 --> local):"
        {
            printf 'FIELD\tR2\t\tLOCAL\n'
            printf 'last_modified\t%s\t-->\t%s\n' \
                "$(jq -r '.last_modified // "?"' "$TMP_META")" "$(echo "$LOCAL_META" | jq -r '.last_modified')"
            printf 'size (mb)\t%s\t-->\t%s\n' \
                "$(jq -r '.size_mb // "?"' "$TMP_META")" "$(echo "$LOCAL_META" | jq -r '.size_mb')"
            printf 'sha256\t%s\t-->\t%s\n' \
                "${REMOTE_SHA:0:8}" "${LOCAL_SHA:0:8}"
        } | column -t -s $'\t'
    else
        echo "No local DB present — restoring fresh from R2."
    fi
else
    echo "No snapshot metadata on R2 — restoring db blob without comparison."
fi

confirm

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
