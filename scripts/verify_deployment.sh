#!/bin/sh
# Copyright (c) 2026 Yash Garad. All rights reserved.
#
# Pre-flight verification for a production deployment.
#
# Run this on the server AFTER `docker compose -f docker-compose.yml
# -f docker-compose.prod.yml up -d` and BEFORE giving anyone the URL.
#
# Every check interrogates the RUNNING SYSTEM rather than reading configuration.
# Checking that docker-compose.prod.yml says DEBUG is off proves only that
# somebody typed it; checking what the live Django process reports proves it is
# actually in force. Several of these checks exist precisely because a file can
# say one thing while the running container does another.
#
# Exit code 0 = every check passed. Non-zero = the number of failures.
#
# Usage:
#   sh scripts/verify_deployment.sh
#   COMPOSE="docker compose" sh scripts/verify_deployment.sh    # against dev

set -u

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
# The URL to probe. MUST match the name Caddy serves, which is SERVER_HOST.
#
# This used to default to https://127.0.0.1, which produced FALSE FAILURES on a
# perfectly healthy server: Caddy issues its certificate for the site address
# (SERVER_HOST) and will not complete a TLS handshake for a bare loopback IP it
# has no certificate for. The connection is refused outright — not a cert
# warning that -k could ignore — so the frontend and health checks both reported
# failures that did not exist. Measured: https://localhost -> 200,
# https://127.0.0.1 -> 000, even with an explicit Host header.
#
# So read SERVER_HOST from the same file the stack was started with. Override
# with SERVER_URL=... if you probe from another machine.
_server_host_from() {
	[ -f "$1" ] || return 1
	sed -n 's/^SERVER_HOST=//p' "$1" | tail -1 | tr -d '"'"'"' \r'
}
_SH="$(_server_host_from .env.production)"
[ -n "$_SH" ] || _SH="$(_server_host_from .env)"
[ -n "$_SH" ] || _SH="localhost"
SERVER_URL="${SERVER_URL:-https://$_SH}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
BACKUP_MAX_AGE_DAYS="${BACKUP_MAX_AGE_DAYS:-2}"

PASS=0
FAIL=0
WARN=0

green()  { printf '  \033[32mPASS\033[0m  %s\n' "$1"; PASS=$((PASS+1)); }
red()    { printf '  \033[31mFAIL\033[0m  %s\n' "$1"; FAIL=$((FAIL+1)); }
yellow() { printf '  \033[33mWARN\033[0m  %s\n' "$1"; WARN=$((WARN+1)); }
detail() { printf '        %s\n' "$1"; }
section(){ printf '\n\033[1m%s\033[0m\n' "$1"; }

# Runs a command in the backend container, quietly.
be() { $COMPOSE exec -T backend "$@" 2>/dev/null; }

printf '\n=============================================================\n'
printf ' College Assistant — production verification\n'
printf ' %s\n' "$(date -u '+%Y-%m-%d %H:%M:%S UTC')"
printf '=============================================================\n'

# ---------------------------------------------------------------- 0. reachable
section "0. Stack is up"

if ! $COMPOSE ps >/dev/null 2>&1; then
	red "cannot talk to the compose project"
	detail "Is Docker running, and are you in the project directory?"
	printf '\nAborting: nothing else can be checked.\n'
	exit 1
fi

RUNNING=$($COMPOSE ps --services --filter status=running 2>/dev/null | tr -d '\r')
for svc in postgres qdrant ollama backend caddy sync_worker; do
	if printf '%s\n' "$RUNNING" | grep -qx "$svc"; then
		green "$svc is running"
	else
		red "$svc is NOT running"
	fi
done

# ---------------------------------------------------------------- 1. DEBUG off
section "1. DEBUG is off"

DEBUG_VAL=$(be python -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
django.setup()
from django.conf import settings
print(settings.DEBUG)" | tr -d '\r ')

case "$DEBUG_VAL" in
	False) green "Django reports DEBUG=False" ;;
	True)  red "Django reports DEBUG=True — tracebacks, settings and SQL are exposed to users"
	       detail "Set DJANGO_DEBUG=false in .env.production and recreate the backend." ;;
	*)     red "could not read DEBUG from the running backend (got: '${DEBUG_VAL:-empty}')" ;;
esac

ENVNAME=$(be sh -c 'echo "$DJANGO_ENV"' | tr -d '\r ')
if [ "$ENVNAME" = "production" ]; then
	green "DJANGO_ENV=production"
else
	red "DJANGO_ENV is '${ENVNAME:-unset}', not 'production'"
	detail "The strict production settings module is NOT in use."
fi

# ---------------------------------------------------------- 2. gunicorn serving
section "2. gunicorn is serving (not runserver)"

PROCS=$(be sh -c 'cat /proc/[0-9]*/cmdline 2>/dev/null | tr "\0" " " | tr "\n" "|"')
if printf '%s' "$PROCS" | grep -q "gunicorn"; then
	green "gunicorn process found"
	WORKERS=$(be sh -c 'ls /proc/[0-9]*/cmdline >/dev/null 2>&1 && grep -l gunicorn /proc/[0-9]*/cmdline 2>/dev/null | wc -l' | tr -d '\r ')
	detail "gunicorn-related processes: ${WORKERS:-unknown}"
else
	red "no gunicorn process in the backend container"
fi

if printf '%s' "$PROCS" | grep -q "runserver"; then
	red "manage.py runserver IS RUNNING — this is Django's development server"
	detail "It is single-threaded and explicitly not for production use."
else
	green "runserver is not running"
fi

# ------------------------------------------------------- 3. frontend is a build
section "3. Frontend is a compiled bundle"

HTML=$(curl -sk --max-time 10 "$SERVER_URL/" 2>/dev/null)
if [ -z "$HTML" ]; then
	red "could not fetch the frontend from $SERVER_URL/"
else
	if printf '%s' "$HTML" | grep -qE '@vite/client|@react-refresh'; then
		red "the Vite DEV SERVER is serving the frontend"
		detail "Found dev-server markers in the HTML. Production must serve a built bundle."
	else
		green "no dev-server markers in the served HTML"
	fi

	# Vite writes name-HASH.js with a HYPHEN and a BASE64 hash. This pattern
	# used to require a dot before the hash, so it never matched a real bundle
	# and reported a warning on a perfectly good deployment.
	if printf '%s' "$HTML" | grep -qE '/assets/[^"]+[.-][0-9a-zA-Z_-]{6,}\.(js|css)'; then
		green "hashed production asset references present"
	else
		yellow "no hashed asset references found — verify the bundle was built"
	fi

	# The header, not just the filename. A hashed name is only useful if the
	# immutable cache rule actually matches it — and it did not: Caddyfile.prod
	# required a hex hash while Vite emits base64, so a 530 KB bundle that never
	# changes was re-downloaded on every single page load. Nothing failed
	# visibly, which is exactly why this is checked rather than assumed.
	ASSET_PATH="$(printf '%s' "$HTML" | grep -oE '/assets/[^"]+\.js' | head -1)"
	if [ -n "$ASSET_PATH" ]; then
		ASSET_CC="$(curl -sk --max-time 10 -D- -o /dev/null "$SERVER_URL$ASSET_PATH" 2>/dev/null | tr -d '\015' | grep -i '^cache-control:' | cut -d' ' -f2-)"
		case "$ASSET_CC" in
			*immutable*) green "hashed assets are served immutable (${ASSET_CC})" ;;
			"")          red  "hashed assets carry NO Cache-Control header"
			             detail "Every page load re-downloads the bundle. Check the @hashed matcher in Caddyfile.prod." ;;
			*)           yellow "hashed assets served with '${ASSET_CC}', expected immutable" ;;
		esac
	fi
fi

# Ollama thread count vs its CPU quota.
#
# A mismatch here does not fail visibly — it makes every answer time out while
# the stack reports itself perfectly healthy, which is how it survived until a
# production request was actually served. See docs/LATENCY.md, 21 Aug 2026.
OLLAMA_CID="$($COMPOSE ps -q ollama 2>/dev/null | tr -d '\r')"
OLLAMA_CPUS=0
if [ -n "$OLLAMA_CID" ]; then
	OLLAMA_CPUS="$(docker inspect "$OLLAMA_CID" --format '{{.HostConfig.NanoCpus}}' 2>/dev/null || echo 0)"
fi
if [ "${OLLAMA_CPUS:-0}" -gt 0 ] 2>/dev/null; then
	CPU_COUNT=$(( OLLAMA_CPUS / 1000000000 ))
	# Read the EFFECTIVE value out of the running backend, not out of a file.
	# The file is what someone wrote; this is what the process actually has.
	NT="$(be sh -c 'echo "$OLLAMA_NUM_THREAD"' 2>/dev/null | tr -d '\r ')"
	if [ -z "$NT" ] || [ "$NT" = "0" ]; then
		red "ollama is capped at ${CPU_COUNT} CPUs but OLLAMA_NUM_THREAD is unset"
		detail "llama.cpp will spawn one thread per HOST core and thrash. Measured 34x slower; every request times out. Set OLLAMA_NUM_THREAD=${CPU_COUNT}."
	elif [ "$NT" -gt "$CPU_COUNT" ] 2>/dev/null; then
		red "OLLAMA_NUM_THREAD=${NT} exceeds the ${CPU_COUNT}-CPU limit on ollama"
		detail "Threads oversubscribe the quota and inference collapses. Set them equal."
	else
		green "OLLAMA_NUM_THREAD=${NT} matches the ${CPU_COUNT}-CPU limit on ollama"
	fi
else
	yellow "could not read ollama's CPU quota — thread/quota check SKIPPED"
	detail "This check silently no-opped on every machine but the author's until 25 Aug 2026. If you see this line, verify OLLAMA_NUM_THREAD by hand against the container's CPU limit before serving anyone."
fi

if $COMPOSE ps --services 2>/dev/null | grep -qx "frontend"; then
	red "a 'frontend' service is defined — the Vite dev server should not exist in production"
else
	green "no separate frontend service (Caddy serves the bundle)"
fi

# --------------------------------------------------------- 4. no default secrets
section "4. No default or example secrets"

SECRET_OUT=$(be python -c "
import os, sys
sys.path.insert(0,'/app')
from config.secret_guards import find_secret_problems
problems = find_secret_problems()
print('OK' if not problems else 'PROBLEMS')
for p in problems:
    print(p)")

if printf '%s' "$SECRET_OUT" | head -1 | grep -q "OK"; then
	green "no default, example or known-burned secrets in use"
elif printf '%s' "$SECRET_OUT" | head -1 | grep -q "PROBLEMS"; then
	red "insecure secrets detected"
	printf '%s\n' "$SECRET_OUT" | tail -n +2 | while IFS= read -r line; do detail "$line"; done
else
	red "could not run the secret guard in the backend container"
fi

# Never print the key itself — only its length.
KEYLEN=$(be python -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
django.setup()
from django.conf import settings
print(len(settings.SECRET_KEY))" | tr -d '\r ')
if [ -n "$KEYLEN" ] && [ "$KEYLEN" -ge 50 ] 2>/dev/null; then
	green "DJANGO_SECRET_KEY is $KEYLEN characters"
else
	red "DJANGO_SECRET_KEY is too short or unreadable (${KEYLEN:-unknown})"
fi

# --- 4b. the secrets FILE itself ----------------------------------------------
# Strong secrets in a world-readable file are not secrets. generate_secrets.sh
# creates .env.production with umask 077 and chmod 600, but the file is edited
# afterwards (three placeholders must be replaced), copied between machines, and
# restored from backups — any of which can widen the mode.
if [ -f .env.production ]; then
	MODE=$(stat -c '%a' .env.production 2>/dev/null || stat -f '%Lp' .env.production 2>/dev/null || echo "")
	if [ -z "$MODE" ]; then
		yellow "could not read the mode of .env.production on this filesystem"
	else
		# Anything readable by group or other. 600 and 400 pass; 640 and 644 do not.
		case "$MODE" in
			*[1-7][0-7] | *[0-7][1-7])
				red ".env.production is mode $MODE — readable beyond its owner"
				detail "it holds the database password and the Django secret key"
				detail "fix with:  chmod 600 .env.production"
				;;
			*)
				green ".env.production is mode $MODE (owner only)"
				;;
		esac
	fi
fi

# --- 4c. who can actually log in ----------------------------------------------
# A deployment can pass every configuration check and still ship with accounts
# nobody intended: load-test users from a demo database, a bootstrap account
# whose file-read password was never changed, an unnoticed superuser. Our own
# reference deployment accumulated 57 such accounts, and nothing could show
# them because there was no way to list accounts at all.
ACCOUNTS=$(be python manage.py list_users --concerns 2>&1)
ACCOUNT_RC=$?
if [ "$ACCOUNT_RC" -eq 0 ] && printf '%s' "$ACCOUNTS" | grep -q "nothing flagged"; then
	green "$(printf '%s' "$ACCOUNTS" | head -1)"
elif printf '%s' "$ACCOUNTS" | grep -q "warrant a look"; then
	red "accounts on this server warrant an access review"
	printf '%s
' "$ACCOUNTS" | sed -n '3,$p' | while IFS= read -r line; do
		[ -n "$line" ] && detail "$line"
	done
else
	yellow "could not run the account review"
fi

# ---------------------------------------------------- 5. read-only role locked down
section "5. rag_agent_ro cannot write"

RO=$(be python manage.py check_rag_agent_ro --check-write)

if printf '%s' "$RO" | grep -q "default_transaction_read_only: on"; then
	green "session default_transaction_read_only is ON"
else
	red "default_transaction_read_only is NOT on"
fi

if printf '%s' "$RO" | grep -q "INSERT correctly rejected"; then
	green "a real INSERT was rejected by Postgres"
else
	red "the write test did NOT confirm rejection"
	detail "Run: $COMPOSE exec backend python manage.py check_rag_agent_ro --check-write"
fi

if printf '%s' "$RO" | grep -q "UNEXPECTED WRITE ACCESS"; then
	red "the role holds WRITE privileges on at least one table"
else
	green "no write privileges on any visible table"
fi

# Per-student tables must not even be visible.
LEAKED=""
for t in students enrollments attendance exam_results fee_payments; do
	if printf '%s' "$RO" | grep -q "public\.$t "; then
		LEAKED="$LEAKED $t"
	fi
done
if [ -n "$LEAKED" ]; then
	red "per-student table(s) readable by the assistant:$LEAKED"
	detail "These must never be in the allowlist. See backend/common/allowlist.py."
else
	green "no per-student tables are readable"
fi

# ------------------------------------------------------------------ 6. backups
section "6. Backups"

if [ ! -f scripts/backup.sh ]; then
	red "scripts/backup.sh is missing"
elif [ ! -d "$BACKUP_DIR" ]; then
	red "no backup directory at $BACKUP_DIR — a backup has never been taken"
	detail "Run: sh scripts/backup.sh"
else
	LATEST=$(ls -1d "$BACKUP_DIR"/*/ 2>/dev/null | sort | tail -1)
	if [ -z "$LATEST" ]; then
		red "$BACKUP_DIR exists but contains no backups"
		detail "Run: sh scripts/backup.sh"
	else
		LATEST=${LATEST%/}
		if [ -f "$LATEST/MANIFEST.txt" ]; then
			green "most recent backup: $(basename "$LATEST") (with manifest)"
		else
			yellow "most recent backup $(basename "$LATEST") has no MANIFEST.txt"
		fi

		DUMP=$(ls -1 "$LATEST"/postgres-*.dump 2>/dev/null | head -1)
		if [ -n "$DUMP" ] && [ "$(wc -c < "$DUMP")" -gt 1024 ]; then
			green "database dump present ($(wc -c < "$DUMP") bytes)"
		else
			red "database dump missing or suspiciously small"
		fi

		if [ -n "$(find "$LATEST" -maxdepth 0 -mtime +"$BACKUP_MAX_AGE_DAYS" 2>/dev/null)" ]; then
			red "most recent backup is older than $BACKUP_MAX_AGE_DAYS days"
			detail "Backups are not running on a schedule. Add the cron entry from DEPLOYMENT.md."
		else
			green "most recent backup is under $BACKUP_MAX_AGE_DAYS days old"
		fi
	fi
fi

# --------------------------------------------------------------- 7. healthchecks
section "7. Health"

AGG=$(curl -sk --max-time 15 "$SERVER_URL/api/health/" 2>/dev/null)
if printf '%s' "$AGG" | grep -q '"status":"ok"'; then
	green "aggregate health reports ok"
	detail "$AGG"
elif [ -n "$AGG" ]; then
	red "aggregate health is NOT ok"
	detail "$AGG"
else
	red "could not reach $SERVER_URL/api/health/"
fi

# Container-level healthchecks, which is what restart:always acts on.
for svc in postgres redis qdrant ollama backend sync_worker caddy; do
	CID=$($COMPOSE ps -q "$svc" 2>/dev/null | tr -d '\r')
	if [ -z "$CID" ]; then
		continue
	fi
	ST=$(docker inspect "$CID" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' 2>/dev/null | tr -d '\r')
	case "$ST" in
		healthy)   green "$svc container healthcheck: healthy" ;;
		none)      yellow "$svc has no container healthcheck defined" ;;
		starting)  yellow "$svc healthcheck still starting" ;;
		*)         red "$svc container healthcheck: $ST" ;;
	esac
done

# HTTP must redirect to HTTPS.
CODE=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "http://127.0.0.1/" 2>/dev/null)
case "$CODE" in
	301|302|307|308) green "plain HTTP redirects to HTTPS ($CODE)" ;;
	"")              yellow "could not test the HTTP->HTTPS redirect" ;;
	*)               red "plain HTTP returned $CODE instead of a redirect" ;;
esac

# Unauthenticated access must be refused.
CODE=$(curl -sk -o /dev/null -w '%{http_code}' --max-time 15 -X POST "$SERVER_URL/api/ask/" \
	-H 'Content-Type: application/json' -d '{"question":"test"}' 2>/dev/null)
if [ "$CODE" = "403" ] || [ "$CODE" = "401" ]; then
	green "unauthenticated /api/ask/ is refused ($CODE)"
else
	red "unauthenticated /api/ask/ returned $CODE — expected 401/403"
fi

# ------------------------------------------------------- 8. the records are there
section "8. Institutional records are loaded"

# WHY THIS SECTION EXISTS
# Until 25 Aug 2026 this script exited 0, every container reported healthy and
# /api/health/ returned "ok" on a database containing nothing but the schema and
# one admin account. SEED_DEMO_DATA is false in production, so that is the exact
# state of a fresh install. Every question then answers "no matching records
# were found" while the go-live gate says READY.
#
# A HALF-loaded import is the worse case: departments present, courses missing,
# answers confident and silently incomplete. Counting per-table catches it;
# a single SELECT 1 never could.

ROWS="$(be python manage.py shell -c "
from academics import models as m
for n in ('Department','Program','Course','Faculty','FeeStructure','ClassSchedule'):
    k = getattr(m, n, None)
    print(n, k.objects.count() if k else 'MISSING')
" 2>/dev/null | tr -d '\r')"

if [ -z "$ROWS" ]; then
	red "could not count institutional records"
	detail "The backend did not answer. If the stack is still starting, re-run in a minute."
else
	EMPTY=0; TOTAL=0
	while read -r NAME COUNT; do
		[ -z "$NAME" ] && continue
		case "$COUNT" in
			''|*[!0-9]*) yellow "$NAME: $COUNT"; continue ;;
		esac
		TOTAL=$(( TOTAL + COUNT ))
		if [ "$COUNT" -eq 0 ]; then
			EMPTY=$(( EMPTY + 1 ))
			yellow "$NAME is empty"
		else
			green "$NAME: $COUNT rows"
		fi
	done <<-ROWEOF
	$ROWS
	ROWEOF

	if [ "$TOTAL" -eq 0 ]; then
		red "the database holds NO institutional records"
		detail "Every question will answer 'no matching records were found'. Import your data first — see DATA_IMPORT.md — then re-run this script."
	elif [ "$EMPTY" -gt 0 ]; then
		yellow "$EMPTY of the core tables are empty — a partial import looks likely"
		detail "Answers drawn from a half-loaded database look authoritative and are silently incomplete. Confirm this is deliberate before opening to students."
	fi
fi

# The search index has to be populated too, or descriptive questions fall back
# to nothing while the vector store still reports itself reachable.
QCOL="${QDRANT_COLLECTION:-college_docs}"
PTS="$(be python -c "
import os, json, urllib.request
url = os.getenv('QDRANT_URL', 'http://qdrant:6333') + '/collections/' + '$QCOL'
try:
    with urllib.request.urlopen(url, timeout=5) as r:
        print(json.load(r)['result']['points_count'])
except Exception:
    print('unreachable')
" 2>/dev/null | tr -d '\r')"

case "$PTS" in
	unreachable|'') yellow "could not read the '$QCOL' search index" ;;
	0)              red "the search index '$QCOL' is empty"
	                detail "The sync worker turns records into searchable text. Check: $COMPOSE logs sync_worker" ;;
	*[!0-9]*)       yellow "unexpected reply reading the search index: $PTS" ;;
	*)              green "search index '$QCOL': $PTS entries" ;;
esac

# ------------------------------------------------------------------- summary
printf '\n=============================================================\n'
printf ' PASS: %d    FAIL: %d    WARN: %d\n' "$PASS" "$FAIL" "$WARN"
printf '=============================================================\n'

if [ "$FAIL" -gt 0 ]; then
	printf '\n\033[31mNOT READY.\033[0m Fix the %d failure(s) above before opening this to students.\n\n' "$FAIL"
	exit "$FAIL"
fi

if [ "$WARN" -gt 0 ]; then
	printf '\n\033[33mPassed with %d warning(s).\033[0m Read them before proceeding.\n\n' "$WARN"
else
	printf '\n\033[32mAll checks passed.\033[0m\n\n'
fi

printf 'Automated checks cannot cover everything. Complete the manual\n'
printf 'pre-flight checklist in DEPLOYMENT.md before going live.\n\n'
exit 0
