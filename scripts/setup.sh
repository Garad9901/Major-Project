#!/bin/sh
# Copyright (c) 2026 Yash Garad. All rights reserved.
#
# GUIDED FIRST-RUN SETUP.
#
# Everything an institution must decide before this system can serve anyone,
# asked once, in order, with the answers written to the two files that hold
# them. It replaces "hand-edit .env after reading a 21 KB deployment guide",
# which is a reasonable instruction for the author and a poor one for a college
# IT department who have been handed a product.
#
# WHAT IT DOES
#   1. checks prerequisites (docker, compose, disk, RAM)
#   2. asks for the institution name, server address and admin contact
#   3. generates all secrets via scripts/generate_secrets.sh - unchanged, so
#      there is one implementation of "make a credential" in this repository
#   4. substitutes the server address into the placeholders that script leaves
#   5. writes config/institution.json from the example
#   6. validates the result and says exactly what is still outstanding
#
# WHAT IT DELIBERATELY DOES NOT DO
#   * print a secret. Not once, not "just this time". Terminal scrollback, shell
#     history and screen-sharing all outlive the moment.
#   * overwrite an existing .env.production or config/institution.json. Rotating
#     a live secret has an order that matters (docs/SECRET_ROTATION.md), and
#     clobbering the file would strand a running stack.
#   * start the stack. Starting downloads ~7.7 GB of models; that should be a
#     separate, deliberate command run when the operator is ready to wait.
#
# Usage:
#   sh scripts/setup.sh                    interactive, production
#   sh scripts/setup.sh --dev              interactive, writes .env for local dev
#   sh scripts/setup.sh --non-interactive \
#        --name "Riverside Institute of Technology" \
#        --host rag.riverside.edu \
#        --email it-helpdesk@riverside.edu

set -eu

# ------------------------------------------------------------------------------
# Locate the repository root, so this works from anywhere.
# ------------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT"

MODE="production"
INTERACTIVE="yes"
INST_NAME=""
SERVER_ADDR=""
CONTACT_EMAIL=""

while [ $# -gt 0 ]; do
	case "$1" in
		--dev) MODE="dev"; shift ;;
		--non-interactive) INTERACTIVE="no"; shift ;;
		--name) INST_NAME="${2:-}"; shift 2 ;;
		--host) SERVER_ADDR="${2:-}"; shift 2 ;;
		--email) CONTACT_EMAIL="${2:-}"; shift 2 ;;
		-h|--help) sed -n '3,40p' "$0"; exit 0 ;;
		*) echo "unknown option: $1" >&2; exit 2 ;;
	esac
done

if [ "$MODE" = "dev" ]; then
	ENV_FILE=".env"
else
	ENV_FILE=".env.production"
fi
INST_FILE="config/institution.json"

say()  { printf '%s\n' "$*"; }
step() { printf '\n=== %s ===\n' "$*"; }
warn() { printf 'WARNING: %s\n' "$*" >&2; }
die()  { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

# ------------------------------------------------------------------------------
# 1. Prerequisites
#
# Checked BEFORE asking any questions. Discovering a missing dependency after
# the operator has typed out their institution's legal name is a small rudeness
# that is entirely avoidable.
# ------------------------------------------------------------------------------
step "Checking prerequisites"

command -v docker >/dev/null 2>&1 || die "docker is not installed or not on PATH."
if docker compose version >/dev/null 2>&1; then
	say "  docker compose      OK"
elif command -v docker-compose >/dev/null 2>&1; then
	warn "found legacy docker-compose. This project targets Compose v2 ('docker compose')."
else
	die "docker compose is not available."
fi
docker info >/dev/null 2>&1 || die "the docker daemon is not running (or this user cannot reach it)."
say "  docker daemon       OK"

# RAM. The container limits total 18.75 GB at first start (17.75 GB once
# ollama-pull exits), plus ~2 GB for the host and Docker. Below that this runs
# but swaps, and swapping during inference turns a 30-second answer into a
# multi-minute one.
#
# This check said 16 GB until 27 August 2026, inherited from a hand-maintained
# total in docker-compose.prod.yml that was never updated when the ollama limit
# was raised from 8 GB to 12 GB. Re-derive with `docker compose config`, not
# from memory.
if [ -r /proc/meminfo ]; then
	TOTAL_KB="$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)"
	TOTAL_GB="$((TOTAL_KB / 1024 / 1024))"
	if [ "$TOTAL_GB" -lt 24 ]; then
		warn "${TOTAL_GB} GB RAM detected. 24 GB is the practical minimum: container limits total 18.75 GB at first start, plus ~2 GB for the host. Expect swapping."
	else
		say "  RAM                 OK (${TOTAL_GB} GB)"
	fi
fi

# Disk. Models ~7.7 GB, images ~3 GB, database and vector store grow from there.
FREE_GB="$(df -Pk "$ROOT" 2>/dev/null | awk 'NR==2 {print int($4/1024/1024)}')" || FREE_GB=""
if [ -n "$FREE_GB" ] && [ "$FREE_GB" -lt 25 ]; then
	warn "${FREE_GB} GB free on this filesystem. Models and images alone need ~11 GB; 25 GB is a sane floor."
elif [ -n "$FREE_GB" ]; then
	say "  Disk                OK (${FREE_GB} GB free)"
fi

# ------------------------------------------------------------------------------
# 2. Refuse to clobber
#
# Both files hold decisions somebody made. Overwriting either silently is how an
# upgrade takes a working deployment down.
# ------------------------------------------------------------------------------
EXISTING=""
[ -e "$ENV_FILE" ] && EXISTING="$EXISTING $ENV_FILE"
[ -e "$INST_FILE" ] && EXISTING="$EXISTING $INST_FILE"
if [ -n "$EXISTING" ]; then
	say ""
	die "already set up — these exist:$EXISTING

Refusing to overwrite them. To reconfigure:
  - identity, colours, allowlist -> edit $INST_FILE directly, then restart the backend
  - a secret                     -> see docs/SECRET_ROTATION.md; the order matters
  - start over from nothing      -> move the files aside first, then re-run this"
fi

# ------------------------------------------------------------------------------
# 3. Questions
# ------------------------------------------------------------------------------
ask() {
	# ask VAR "prompt" "default"
	_var="$1"; _prompt="$2"; _default="${3:-}"
	eval "_current=\${$_var}"
	[ -n "$_current" ] && return 0
	if [ "$INTERACTIVE" = "no" ]; then
		[ -n "$_default" ] || die "--non-interactive needs a value for $_var"
		eval "$_var=\$_default"
		return 0
	fi
	if [ -n "$_default" ]; then
		printf '%s [%s]: ' "$_prompt" "$_default"
	else
		printf '%s: ' "$_prompt"
	fi
	if ! read -r _answer; then
		# EOF, not a blank line. Treating the two the same made this loop
		# forever when stdin was a pipe, a provisioning tool, or
		# `ssh host 'sh scripts/setup.sh'` — 762,000 lines in 8 seconds.
		printf '\n'
		die "no input available (stdin is not a terminal). Re-run with --non-interactive plus --name/--host/--email."
	fi
	[ -z "$_answer" ] && _answer="$_default"
	eval "$_var=\$_answer"
}

step "Your institution"
say "These appear on the sign-in screen and in answers. They can be changed"
say "later by editing $INST_FILE and restarting the backend."
say ""

while [ -z "$INST_NAME" ]; do
	ask INST_NAME "Institution's full name (e.g. Riverside Institute of Technology)"
	[ -n "$INST_NAME" ] || say "  A name is required — the sign-in screen has nothing to show without it."
done

if [ "$MODE" = "dev" ]; then
	: "${SERVER_ADDR:=localhost}"
else
	while [ -z "$SERVER_ADDR" ]; do
		say ""
		say "The address users will type in their browser. For a deployment reachable"
		say "from the internet this must be a real DNS name pointing at this server —"
		say "Caddy uses it to obtain the TLS certificate."
		ask SERVER_ADDR "Server address (e.g. rag.riverside.edu)"
		case "$SERVER_ADDR" in
			*" "*|*"/"*|http*) say "  Just the hostname — no scheme, no path, no spaces."; SERVER_ADDR="" ;;
		esac
	done
fi

say ""
say "Shown to users when something fails and they need a human."
ask CONTACT_EMAIL "IT support email (optional, press enter to skip)" " "
[ "$CONTACT_EMAIL" = " " ] && CONTACT_EMAIL=""

# ------------------------------------------------------------------------------
# 4. Secrets
#
# Delegated to generate_secrets.sh rather than reimplemented. One implementation
# of "make a credential" in this repository means one place to review, and one
# place to fix if the randomness source is ever found wanting.
# ------------------------------------------------------------------------------
step "Generating secrets"

if [ "$MODE" = "dev" ]; then
	sh "$SCRIPT_DIR/generate_secrets.sh" "$ENV_FILE" | grep -E '^(WARNING|ERROR)' || true
	# Development runs over plain HTTP on localhost, so the production-only
	# hardening has to come back off or nothing is reachable.
	TMP="$(mktemp)"
	sed -e 's/^DJANGO_ENV=production/DJANGO_ENV=development/' \
	    -e 's/^DJANGO_DEBUG=false/DJANGO_DEBUG=true/' \
	    -e 's/^COOKIE_SECURE=true/COOKIE_SECURE=false/' \
	    "$ENV_FILE" > "$TMP"
	cat "$TMP" > "$ENV_FILE"
	rm -f "$TMP"
	chmod 600 "$ENV_FILE"
else
	# Do NOT swallow this. generate_secrets.sh is the only thing that warns
	# when the machine has fewer CPUs than inference is allocated, which is
	# the difference between 20-second answers and universal timeouts.
	sh "$SCRIPT_DIR/generate_secrets.sh" "$ENV_FILE" | grep -E '^(WARNING|ERROR)' || true
fi
say "  $ENV_FILE created (permissions 600). No secret has been printed."

# Substitute the address into the three placeholders generate_secrets.sh leaves.
TMP="$(mktemp)"
sed "s|CHANGEME-SERVER-ADDRESS|$SERVER_ADDR|g" "$ENV_FILE" > "$TMP"
cat "$TMP" > "$ENV_FILE"
rm -f "$TMP"
chmod 600 "$ENV_FILE"
say "  server address set to '$SERVER_ADDR'"

# ------------------------------------------------------------------------------
# 5. Institution config
#
# Built with python when available (correct JSON escaping for names containing
# quotes, ampersands or non-ASCII), falling back to sed. A college called
# "St. Mary's" must not produce a broken config file.
# ------------------------------------------------------------------------------
step "Writing $INST_FILE"

# Being on PATH is not the same as working. On Windows, `python` resolves to
# a Microsoft Store stub that prints an error and exits; on some slim images
# `python3` is a dangling symlink. Both pass `command -v` and then fail. So
# the test is whether it actually runs a program.
PY=""
for CANDIDATE in python3 python; do
	if command -v "$CANDIDATE" >/dev/null 2>&1 && "$CANDIDATE" -c "pass" >/dev/null 2>&1; then
		PY="$CANDIDATE"
		break
	fi
done

if [ -n "$PY" ]; then
	INST_NAME="$INST_NAME" CONTACT_EMAIL="$CONTACT_EMAIL" "$PY" - <<'PYEOF'
import json, os, re

src = open("config/institution.example.json", encoding="utf-8").read()
# Strip //-free JSON is already valid; the example uses _-prefixed keys for docs
# rather than comments, so it parses as-is.
data = json.loads(src)
data["institution"]["name"] = os.environ["INST_NAME"]
data["institution"]["contact_email"] = os.environ.get("CONTACT_EMAIL", "")
with open("config/institution.json", "w", encoding="utf-8") as fh:
    json.dump(data, fh, indent=2, ensure_ascii=False)
    fh.write("\n")
PYEOF
else
	warn "no working python found; falling back to sed."
	# & and backslash are special in a sed REPLACEMENT (& means "the whole
	# match"), so a college called "Mary's College & Institute" would silently
	# corrupt the file. Escape them, and the delimiter, before substituting.
	SAFE_NAME="$(printf '%s' "$INST_NAME" | sed -e 's/[\\&|]/\\&/g')"
	SAFE_EMAIL="$(printf '%s' "$CONTACT_EMAIL" | sed -e 's/[\\&|]/\\&/g')"
	sed -e "s|\"name\": \"\"|\"name\": \"$SAFE_NAME\"|" \
	    -e "s|\"contact_email\": \"\"|\"contact_email\": \"$SAFE_EMAIL\"|" \
	    config/institution.example.json > "$INST_FILE"
	# A mangled substitution yields invalid JSON, which the backend would fall
	# back over at boot. Fail here instead, where the operator is watching.
	if ! grep -qF "$INST_NAME" "$INST_FILE"; then
		rm -f "$INST_FILE"   # do not strand a corrupt file that blocks a re-run
		die "failed to write the institution name into $INST_FILE"
	fi
fi
say "  institution name set"

# ------------------------------------------------------------------------------
# 6. Validate
#
# The point of a setup script is that it tells you whether it worked. Reporting
# success and leaving the operator to discover a placeholder at first boot would
# be worse than no script at all.
# ------------------------------------------------------------------------------
step "Validating"

FAILED=0
fail() { printf '  FAIL  %s\n' "$*"; FAILED=$((FAILED + 1)); }
pass() { printf '  ok    %s\n' "$*"; }

[ -f "$ENV_FILE" ] && pass "$ENV_FILE exists" || fail "$ENV_FILE missing"

PERMS="$(stat -c '%a' "$ENV_FILE" 2>/dev/null || stat -f '%Lp' "$ENV_FILE" 2>/dev/null || echo '')"
if [ "$PERMS" = "600" ]; then
	pass "$ENV_FILE permissions are 600"
elif [ -n "$PERMS" ]; then
	fail "$ENV_FILE permissions are $PERMS, expected 600"
fi

if grep -q 'CHANGEME' "$ENV_FILE" 2>/dev/null; then
	fail "$ENV_FILE still contains CHANGEME placeholders:"
	grep -n 'CHANGEME' "$ENV_FILE" | sed 's/^/          line /'
else
	pass "no CHANGEME placeholders remain"
fi

# Every secret must be present AND non-trivial. A key that exists but is empty
# passes a "is it set" check and fails at runtime.
for KEY in DJANGO_SECRET_KEY POSTGRES_PASSWORD RAG_AGENT_RO_PASSWORD; do
	VALUE="$(grep "^${KEY}=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2-)"
	if [ -z "$VALUE" ]; then
		fail "$KEY is empty"
	elif [ "${#VALUE}" -lt 24 ]; then
		fail "$KEY is only ${#VALUE} characters"
	else
		pass "$KEY set (${#VALUE} chars)"
	fi
done

if [ -f "$INST_FILE" ]; then
	pass "$INST_FILE exists"
	if [ -n "$PY" ]; then
		if "$PY" -c "
import json,sys
d=json.load(open('$INST_FILE',encoding='utf-8'))
name=(d.get('institution') or {}).get('name') or ''
sys.exit(0 if name.strip() else 1)" 2>/dev/null; then
			pass "institution name is set"
		else
			fail "institution name is empty in $INST_FILE"
		fi
	fi
else
	fail "$INST_FILE missing"
fi

# Both files must be ignored by git. This is the check that stops a live
# credential reaching a public repository, so it runs every time.
if command -v git >/dev/null 2>&1 && [ -d .git ]; then
	for F in "$ENV_FILE" "$INST_FILE"; do
		if git check-ignore -q "$F" 2>/dev/null; then
			pass "$F is gitignored"
		else
			fail "$F is NOT gitignored — it would be committed"
		fi
	done
fi

# ------------------------------------------------------------------------------
# 7. What next
# ------------------------------------------------------------------------------
if [ "$FAILED" -gt 0 ]; then
	say ""
	die "$FAILED check(s) failed. Fix the above before starting the stack."
fi

step "Setup complete"
say ""
say "Institution : $INST_NAME"
say "Address     : $SERVER_ADDR"
say "Secrets     : $ENV_FILE (600, not printed, not committed)"
say ""
say "STILL TO DO — none of these can be decided for you:"
say ""
say "  1. Start the stack. First run downloads ~7.7 GB of models and takes"
say "     20-40 minutes on a typical connection:"
if [ "$MODE" = "dev" ]; then
	say "         docker compose up -d"
else
	say "         docker compose --env-file .env.production \\"
	say "             -f docker-compose.yml -f docker-compose.prod.yml up -d"
fi
say ""
say "  2. Read the bootstrap admin password out of $ENV_FILE (STAFF_PASSWORD),"
say "     sign in, and CHANGE IT. Then create real per-person accounts:"
if [ "$MODE" = "dev" ]; then
	say "         docker compose exec backend python manage.py create_user --help"
else
	say "         docker compose --env-file .env.production \\"
	say "             -f docker-compose.yml -f docker-compose.prod.yml \\"
	say "             exec backend python manage.py create_user --help"
fi
say ""
say "  3. Import your records. The system starts EMPTY on purpose:"
say "         see DATA_IMPORT.md"
say ""
say "  4. Add your own web pages to the allowlist in $INST_FILE."
say "     Both entries ship disabled and point at example.edu."
say ""
say "  5. Verify the deployment:"
say "         sh scripts/verify_deployment.sh"
say ""
