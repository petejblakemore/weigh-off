#!/bin/bash
# Nightly backup for The Weigh Off SQLite database.
# Modelled on the CMMS backup.sh: safe snapshot, integrity check, gzip, retention.
set -euo pipefail

DB="/opt/weigh-off-server/weighoff.db"
LOCAL_DIR="/home/pete/backups/weigh-off"
STAMP="$(date +%Y%m%d-%H%M%S)"
LOCAL_FILE="$LOCAL_DIR/weighoff-$STAMP.db"

mkdir -p "$LOCAL_DIR"

# Consistent snapshot (handles the WAL / locking correctly — a plain cp can catch a half-written DB)
sqlite3 "$DB" ".backup '$LOCAL_FILE'"

# Verify the snapshot isn't corrupt before trusting it
if ! sqlite3 "$LOCAL_FILE" "PRAGMA integrity_check;" | grep -q "^ok$"; then
  echo "Integrity check FAILED for $LOCAL_FILE" >&2
  rm -f "$LOCAL_FILE"
  exit 1
fi

gzip "$LOCAL_FILE"

# Keep the last 30 nightly backups locally
ls -1t "$LOCAL_DIR"/weighoff-*.db.gz | tail -n +31 | xargs -r rm -f

echo "Backup complete: $(basename "$LOCAL_FILE").gz"
