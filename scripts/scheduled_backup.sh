#!/bin/sh
# Copyright (c) 2026 Yash Garad. All rights reserved.
#
# THE BACKUP THAT RUNS WITHOUT ANYONE REMEMBERING TO SCHEDULE IT.
#
# scripts/backup.sh is the operator's manual tool and stays exactly as it is.
# This is the unattended one, run by the `backup` service in docker-compose.
#
# WHY THIS EXISTS AT ALL
# The documented procedure was "add this line to crontab". The production audit
# then found that the entry had never actually been installed, and
# verify_deployment.sh has been failing on "most recent backup is older than 2
# days" ever since. That is the whole problem with a documented manual step: it
# is indistinguishable, from the outside, from a forgotten one. A product a
# stranger installs cannot depend on them remembering.
#
# WHY IT DOES NOT MOUNT THE DOCKER SOCKET
# scripts/backup.sh shells out to `docker compose exec postgres pg_dump`. Doing
# that from inside a container needs /var/run/docker.sock, and mounting the
# docker socket into a long-running service is equivalent to giving it root on
# the host — a serious privilege escalation to accept in exchange for a cron
# replacement. So this connects to Postgres over the internal network with
# pg_dump instead, and to Qdrant over its HTTP API. It needs no privilege beyond
# reaching two services it already shares a network with.
#
# WHAT IT STILL DOES NOT DO
# Copy anything off this machine. A backup on the same disk as the database does
# not survive that disk failing, which is the most likely thing it needs to
# survive. Shipping archives off-box remains an operator decision — see
# DEPLOYMENT.md — because where they should go is a question only the
# institution can answer.

set -eu

BACKUP_DIR="${BACKUP_DIR:-/backups}"
INTERVAL_HOURS="${BACKUP_INTERVAL_HOURS:-24}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
QDRANT_URL="${QDRANT_URL:-http://qdrant:6333}"
QDRANT_COLLECTION="${QDRANT_COLLECTION:-college_docs}"

log() { printf '%s [backup] %s\n' "$(date -u '+%Y-%m-%d %H:%M:%S')" "$*"; }

run_once() {
	STAMP="$(date -u '+%Y%m%d-%H%M%S')"
	DEST="$BACKUP_DIR/$STAMP"
	mkdir -p "$DEST"

	log "starting $STAMP"

	# --- Postgres: the system of record -------------------------------------
	# FORMAT AND FILENAME MATCH scripts/backup.sh EXACTLY, and that is a
	# requirement rather than tidiness: scripts/restore.sh looks for
	# postgres-<db>.dump and validates it with `pg_restore --list`, which only
	# works on the custom format. A scheduled backup that restore.sh cannot read
	# is not a backup. The two paths must produce interchangeable artefacts, so
	# an operator restoring at 3am does not have to know which one wrote it.
	DUMP="$DEST/postgres-${POSTGRES_DB}.dump"
	if PGPASSWORD="$POSTGRES_PASSWORD" pg_dump \
		-h "${POSTGRES_HOST:-postgres}" -p "${POSTGRES_PORT:-5432}" \
		-U "$POSTGRES_USER" -d "$POSTGRES_DB" \
		--format=custom --no-owner --no-privileges \
		-f "$DUMP" 2>"$DEST/pg_dump.err"; then
		rm -f "$DEST/pg_dump.err"
		log "  $(basename "$DUMP") written ($(wc -c < "$DUMP") bytes)"
	else
		# INCOMPLETE BACKUPS ARE WORSE THAN NO BACKUP, because the directory
		# exists and the next run's age check is satisfied by it. Remove it.
		log "  ERROR: pg_dump failed — $(tail -1 "$DEST/pg_dump.err" 2>/dev/null)"
		rm -rf "$DEST"
		return 1
	fi

	# VERIFY THE ARCHIVE IS READABLE, not merely that a file appeared. This is
	# the same check restore.sh makes before it will touch a dump, run now while
	# somebody could still act on a failure, rather than during the restore.
	if ! PGPASSWORD="$POSTGRES_PASSWORD" pg_restore --list "$DUMP" >/dev/null 2>&1; then
		log "  ERROR: pg_restore cannot read the dump just written — discarding it"
		rm -rf "$DEST"
		return 1
	fi

	# --- Qdrant: derived, but expensive to rebuild --------------------------
	# Best-effort on purpose. The vector store can be rebuilt from Postgres by
	# the sync worker, so a database dump without a vector snapshot is still a
	# usable backup and must not be discarded for want of one.
	SNAP="$(wget -qO- --post-data='' \
		"$QDRANT_URL/collections/$QDRANT_COLLECTION/snapshots" 2>/dev/null || true)"
	SNAP_NAME="$(printf '%s' "$SNAP" | sed -n 's/.*"name":"\([^"]*\)".*/\1/p')"
	if [ -n "$SNAP_NAME" ] && wget -qO "$DEST/qdrant-$SNAP_NAME" \
		"$QDRANT_URL/collections/$QDRANT_COLLECTION/snapshots/$SNAP_NAME" 2>/dev/null; then
		log "  qdrant snapshot saved ($SNAP_NAME)"
	else
		log "  WARNING: no qdrant snapshot this run — the database dump is still valid"
	fi

	# --- manifest, so a restorer knows what they are holding ----------------
	{
		echo "created_utc=$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
		echo "database=$POSTGRES_DB"
		echo "qdrant_collection=$QDRANT_COLLECTION"
		echo "qdrant_snapshot=${SNAP_NAME:-none}"
		echo "written_by=scripts/scheduled_backup.sh"
	} > "$DEST/manifest.txt"

	# --- prune ---------------------------------------------------------------
	# Deletes only directories matching the timestamp shape this script writes,
	# so a stray file in BACKUP_DIR is never removed by it.
	find "$BACKUP_DIR" -maxdepth 1 -type d -name '20*-*' -mtime "+$RETENTION_DAYS" \
		-exec rm -rf {} + 2>/dev/null || true

	log "done $STAMP (keeping $RETENTION_DAYS days)"
}

log "scheduler started: every ${INTERVAL_HOURS}h, retaining ${RETENTION_DAYS} days, into $BACKUP_DIR"

# Runs once at startup rather than sleeping first. A stack that has just been
# deployed, or just recovered from an outage, is exactly when you most want a
# recent backup — and waiting a full interval means the first day of a new
# deployment has none at all.
while true; do
	run_once || log "this run failed; will retry at the next interval"
	sleep "$((INTERVAL_HOURS * 3600))"
done
