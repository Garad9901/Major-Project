#!/bin/sh
# Copyright (c) 2026 Yash Garad. All rights reserved.
#
# Backs up both stateful stores: the PostgreSQL database (the system of record)
# and the Qdrant vector collection (derived, but expensive to rebuild).
#
# WHAT THIS DOES NOT DO
# It writes to a directory on THIS server. A backup sitting on the same disk as
# the database does not survive the disk failing, which is the single most
# likely thing it needs to survive. Copying each archive off this machine is a
# MANUAL step and it is not optional — see the reminder printed at the end and
# the procedure in DEPLOYMENT.md.
#
# Usage:
#   sh scripts/backup.sh                 # uses defaults below
#   BACKUP_DIR=/mnt/backups sh scripts/backup.sh
#   BACKUP_RETENTION_DAYS=30 sh scripts/backup.sh

set -eu

# Overridable so the same script can be exercised against a development stack
# during a restore rehearsal without editing it.
# Production is configured from .env.production, and Compose only reads that
# file for ${VAR} interpolation when it is passed via --env-file. Without it,
# values like POSTGRES_USER/POSTGRES_DB resolve from .env (or fall back to
# defaults) and can differ from what the running stack actually uses.
#
# Detected rather than hardcoded so this script still works on a development
# machine, where .env.production does not exist.
if [ -f .env.production ]; then
	_ENVFILE="--env-file .env.production"
else
	_ENVFILE=""
fi
COMPOSE="${COMPOSE:-docker compose $_ENVFILE -f docker-compose.yml -f docker-compose.prod.yml}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
STAMP="$(date -u '+%Y%m%d-%H%M%S')"

POSTGRES_USER="${POSTGRES_USER:-postgres}"
POSTGRES_DB="${POSTGRES_DB:-college_rag}"
QDRANT_COLLECTION="${QDRANT_COLLECTION:-college_docs}"

DEST="$BACKUP_DIR/$STAMP"

echo "Backup $STAMP -> $DEST"
mkdir -p "$DEST"
chmod 700 "$BACKUP_DIR" 2>/dev/null || true
chmod 700 "$DEST" 2>/dev/null || true

# --- 1. PostgreSQL --------------------------------------------------------------
# --format=custom (not plain SQL) because it is compressed, and because
# pg_restore can then selectively restore and reorder to satisfy dependencies.
# Streamed straight out of the container so no temporary copy is left inside it.
echo "  [1/3] pg_dump ${POSTGRES_DB}..."
if ! $COMPOSE exec -T postgres pg_dump \
        -U "$POSTGRES_USER" \
        -d "$POSTGRES_DB" \
        --format=custom \
        --no-owner \
        --no-privileges \
    > "$DEST/postgres-${POSTGRES_DB}.dump"; then
	echo "  ERROR: pg_dump failed. Removing the incomplete backup directory."
	rm -rf "$DEST"
	exit 1
fi

# A dump that exists but is empty is worse than no dump, because it looks like
# success. Fail loudly on a suspiciously small file.
DUMP_SIZE=$(wc -c < "$DEST/postgres-${POSTGRES_DB}.dump")
if [ "$DUMP_SIZE" -lt 1024 ]; then
	echo "  ERROR: dump is only ${DUMP_SIZE} bytes — almost certainly a failure."
	rm -rf "$DEST"
	exit 1
fi
echo "        ${DUMP_SIZE} bytes"

# --- 2. Qdrant ------------------------------------------------------------------
# Qdrant's snapshot API writes a snapshot inside the container, which is then
# copied out. This is derived data — it can be rebuilt by re-running the sync
# worker over the database — so a failure here is a WARNING, not fatal: a
# database backup without a vector snapshot is still a usable backup.
echo "  [2/3] qdrant snapshot of '${QDRANT_COLLECTION}'..."
# Content-Length: 0 is REQUIRED. Without it qdrant rejects the bodyless POST
# with 400 Bad Request — confirmed against the running service.
SNAP_JSON=$($COMPOSE exec -T qdrant bash -c \
	"exec 3<>/dev/tcp/127.0.0.1/6333; { echo 'POST /collections/${QDRANT_COLLECTION}/snapshots HTTP/1.0'; echo 'Content-Length: 0'; echo; } >&3; cat <&3" 2>/dev/null || true)

SNAP_NAME=$(printf '%s' "$SNAP_JSON" | tr ',' '\n' | grep -o '"name":"[^"]*"' | head -1 | cut -d'"' -f4 || true)

if [ -n "${SNAP_NAME:-}" ]; then
	CID=$($COMPOSE ps -q qdrant)
	if docker cp "$CID:/qdrant/snapshots/${QDRANT_COLLECTION}/${SNAP_NAME}" \
	           "$DEST/qdrant-${QDRANT_COLLECTION}.snapshot" 2>/dev/null; then
		echo "        $(wc -c < "$DEST/qdrant-${QDRANT_COLLECTION}.snapshot") bytes"
		# Remove the in-container copy so /qdrant/snapshots does not grow forever.
		docker exec "$CID" rm -f "/qdrant/snapshots/${QDRANT_COLLECTION}/${SNAP_NAME}" 2>/dev/null || true
	else
		echo "        WARNING: snapshot created but could not be copied out."
	fi
else
	echo "        WARNING: could not create a Qdrant snapshot."
	echo "        The database dump is still valid. The vector index can be"
	echo "        rebuilt by letting sync_worker re-embed after a restore."
fi

# --- 3. Manifest ----------------------------------------------------------------
# Records what the backup contains and the checksums to verify it later.
echo "  [3/3] manifest..."
{
	echo "backup_timestamp_utc: $STAMP"
	echo "postgres_db:          $POSTGRES_DB"
	echo "qdrant_collection:    $QDRANT_COLLECTION"
	echo "created_by:           $(id -un 2>/dev/null || echo unknown)@$(hostname 2>/dev/null || echo unknown)"
	echo ""
	echo "files:"
	for f in "$DEST"/*; do
		[ "$(basename "$f")" = "MANIFEST.txt" ] && continue
		echo "  $(basename "$f")  $(wc -c < "$f") bytes  sha256=$(sha256sum "$f" 2>/dev/null | cut -d' ' -f1 || echo unavailable)"
	done
} > "$DEST/MANIFEST.txt"

# --- retention ------------------------------------------------------------------
# Prune old backups AFTER a successful new one, never before — pruning first
# would mean a failed backup leaves you with fewer copies than you started with.
echo "  pruning backups older than ${RETENTION_DAYS} days..."
PRUNED=0
for d in "$BACKUP_DIR"/*/; do
	[ -d "$d" ] || continue
	[ "$(basename "$d")" = "$STAMP" ] && continue
	if [ -n "$(find "$d" -maxdepth 0 -mtime +"$RETENTION_DAYS" 2>/dev/null)" ]; then
		rm -rf "$d"
		PRUNED=$((PRUNED + 1))
	fi
done
echo "        pruned $PRUNED"

echo ""
echo "Backup complete: $DEST"
echo ""
echo "  !! THIS BACKUP IS ON THE SAME MACHINE AS THE DATABASE !!"
echo "  Copy it somewhere else now. A backup that has only ever existed on one"
echo "  disk does not protect you from that disk failing. For example:"
echo "      scp -r $DEST user@another-host:/path/to/backups/"
echo ""
echo "  A backup you have never restored from is not a backup. Test it:"
echo "      sh scripts/restore.sh --dry-run $DEST"
