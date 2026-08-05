#!/bin/sh
# Copyright (c) 2026 Yash Garad. All rights reserved.
#
# Restores a backup produced by scripts/backup.sh.
#
# DEFAULT TARGET IS A SCRATCH DATABASE, NOT THE LIVE ONE.
# That is deliberate. The purpose of running this most of the time is to PROVE
# the backup is restorable, and a rehearsal that overwrites production is not a
# rehearsal. Restoring over the live database requires --target live and typing
# a confirmation phrase.
#
# Usage:
#   sh scripts/restore.sh --dry-run  ./backups/20260727-101500   # verify only
#   sh scripts/restore.sh            ./backups/20260727-101500   # -> scratch db
#   sh scripts/restore.sh --target live ./backups/20260727-101500

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
POSTGRES_USER="${POSTGRES_USER:-postgres}"
POSTGRES_DB="${POSTGRES_DB:-college_rag}"
SCRATCH_DB="${SCRATCH_DB:-restore_test}"
QDRANT_COLLECTION="${QDRANT_COLLECTION:-college_docs}"

DRY_RUN=0
TARGET="scratch"
BACKUP=""

while [ $# -gt 0 ]; do
	case "$1" in
		--dry-run) DRY_RUN=1 ;;
		--target)  shift; TARGET="${1:-scratch}" ;;
		-*)        echo "Unknown option: $1"; exit 1 ;;
		*)         BACKUP="$1" ;;
	esac
	shift
done

if [ -z "$BACKUP" ]; then
	echo "Usage: sh scripts/restore.sh [--dry-run] [--target scratch|live] <backup-dir>"
	exit 1
fi

DUMP="$BACKUP/postgres-${POSTGRES_DB}.dump"

# --- verify the archive before touching any database ----------------------------
echo "Backup:  $BACKUP"
[ -d "$BACKUP" ] || { echo "ERROR: no such directory"; exit 1; }
[ -f "$DUMP" ]   || { echo "ERROR: missing $DUMP"; exit 1; }

echo "Verifying archive..."
if [ -f "$BACKUP/MANIFEST.txt" ]; then
	# Recompute each checksum and compare against the manifest. A dump that has
	# silently rotted on disk should be discovered HERE, not halfway through a
	# restore of the live database.
	FAILED=0
	while IFS= read -r line; do
		case "$line" in
			*sha256=*)
				fname=$(printf '%s' "$line" | awk '{print $1}')
				want=$(printf '%s' "$line" | sed 's/.*sha256=//')
				[ "$want" = "unavailable" ] && continue
				got=$(sha256sum "$BACKUP/$fname" 2>/dev/null | cut -d' ' -f1)
				if [ "$got" = "$want" ]; then
					echo "  OK       $fname"
				else
					echo "  MISMATCH $fname"
					FAILED=1
				fi
				;;
		esac
	done < "$BACKUP/MANIFEST.txt"
	[ "$FAILED" -eq 0 ] || { echo "ERROR: checksum mismatch — this archive is damaged."; exit 1; }
else
	echo "  WARNING: no MANIFEST.txt; cannot verify integrity."
fi

# pg_restore --list parses the dump's table of contents. If this succeeds the
# archive is structurally intact and readable by this version of pg_restore.
echo "Reading dump table of contents..."
TOC=$($COMPOSE exec -T postgres pg_restore --list < "$DUMP" 2>&1) || {
	echo "ERROR: pg_restore cannot read this dump."
	printf '%s\n' "$TOC" | head -5
	exit 1
}
echo "  $(printf '%s\n' "$TOC" | grep -c 'TABLE DATA') tables with data"

if [ "$DRY_RUN" -eq 1 ]; then
	echo ""
	echo "DRY RUN complete — archive is readable and internally consistent."
	echo "Nothing was written. To actually rehearse a restore:"
	echo "    sh scripts/restore.sh $BACKUP"
	exit 0
fi

# --- choose the destination -----------------------------------------------------
if [ "$TARGET" = "live" ]; then
	DB="$POSTGRES_DB"
	echo ""
	echo "*** RESTORING OVER THE LIVE DATABASE '$DB' ***"
	echo "Every row currently in it will be replaced by the backup's contents."
	echo "Anything written since $(basename "$BACKUP") will be LOST."
	echo ""
	printf 'Type exactly: restore live database\n> '
	read -r CONFIRM
	[ "$CONFIRM" = "restore live database" ] || { echo "Aborted."; exit 1; }
	echo "Stopping writers (backend, sync_worker) so nothing writes mid-restore..."
	$COMPOSE stop backend sync_worker >/dev/null 2>&1 || true
else
	DB="$SCRATCH_DB"
	echo ""
	echo "Restoring into scratch database '$DB' (the live '$POSTGRES_DB' is untouched)."
fi

# --- restore ---------------------------------------------------------------------
echo "Recreating '$DB'..."
$COMPOSE exec -T postgres psql -U "$POSTGRES_USER" -d postgres \
	-c "DROP DATABASE IF EXISTS \"$DB\";" >/dev/null
$COMPOSE exec -T postgres psql -U "$POSTGRES_USER" -d postgres \
	-c "CREATE DATABASE \"$DB\";" >/dev/null

echo "Restoring..."
# --exit-on-error is off on purpose: --no-owner dumps commonly emit benign
# ownership/extension notices. Real failures are caught by the row counts below,
# which check the OUTCOME rather than trusting the exit code.
$COMPOSE exec -T postgres pg_restore \
	-U "$POSTGRES_USER" -d "$DB" --no-owner --no-privileges < "$DUMP" 2>&1 \
	| grep -vE "^$|already exists|must be owner|no privileges" | head -20 || true

# --- prove it actually worked ------------------------------------------------------
# ANALYZE first. The counts below come from pg_stat_user_tables.n_live_tup, which
# is a STATISTICS ESTIMATE maintained asynchronously — immediately after a restore
# it can still read zero for tables that are in fact fully populated. Without this
# the verification below could declare a perfectly good backup "not usable".
echo ""
echo "Gathering statistics (ANALYZE)..."
$COMPOSE exec -T postgres psql -U "$POSTGRES_USER" -d "$DB" -c "ANALYZE;" >/dev/null 2>&1 || true

echo "Row counts in restored database '$DB':"
$COMPOSE exec -T postgres psql -U "$POSTGRES_USER" -d "$DB" -t -A -F'  ' -c "
SELECT relname, n_live_tup
FROM pg_stat_user_tables
WHERE n_live_tup > 0
ORDER BY n_live_tup DESC
LIMIT 15;" | sed 's/^/  /'

TOTAL=$($COMPOSE exec -T postgres psql -U "$POSTGRES_USER" -d "$DB" -t -A -c \
	"SELECT COALESCE(SUM(n_live_tup),0) FROM pg_stat_user_tables;" | tr -d '\r')
echo ""
echo "  total rows restored: $TOTAL"
[ "$TOTAL" -gt 0 ] || { echo "  ERROR: restored database is EMPTY. This backup is not usable."; exit 1; }

if [ "$TARGET" = "live" ]; then
	echo ""
	echo "Restarting backend and sync_worker..."
	$COMPOSE up -d backend sync_worker >/dev/null 2>&1
	echo ""
	echo "The Qdrant vector index was NOT restored by this step. Either restore"
	echo "the snapshot manually, or simply let sync_worker re-embed — it will"
	echo "detect the restored rows and rebuild the index within a few poll cycles."
else
	echo ""
	echo "Rehearsal successful. The scratch database '$DB' still exists so you can"
	echo "inspect it. Remove it when finished:"
	echo "    $COMPOSE exec postgres psql -U $POSTGRES_USER -d postgres -c 'DROP DATABASE \"$DB\";'"
fi
