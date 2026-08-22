#!/bin/sh
# Copyright (c) 2026 Yash Garad. All rights reserved.
#
# Generates a fresh .env.production with new, unrelated secrets.
#
# DESIGN NOTES
#   * Secrets are written ONLY to the output file, never to stdout. Terminal
#     scrollback, shell history and CI logs all outlive the terminal window;
#     printing a password "just once" is how it ends up in three of them.
#   * The file is created with 600 permissions BEFORE anything is written to it,
#     so there is no window in which it exists world-readable.
#   * An existing .env.production is never silently overwritten. Rotating a live
#     secret has ordering consequences (see docs/SECRET_ROTATION.md); clobbering
#     the file would strand the running stack.
#   * Values shared with the development .env are NOT reused. The production
#     server should have no credential in common with a developer laptop.
#
# Usage:  sh scripts/generate_secrets.sh [output-file]

set -eu

OUT="${1:-.env.production}"

# --- refuse to clobber ---------------------------------------------------------
if [ -e "$OUT" ]; then
	echo "ERROR: $OUT already exists."
	echo
	echo "Refusing to overwrite it — rotating a secret on a running stack has an"
	echo "order that matters. See docs/SECRET_ROTATION.md."
	echo
	echo "To generate a fresh file for comparison, pass another path:"
	echo "    sh scripts/generate_secrets.sh .env.production.new"
	exit 1
fi

# --- pick a source of randomness ----------------------------------------------
# openssl is present in essentially every server image; /dev/urandom is the
# fallback. Both are cryptographically suitable. `head -c` on urandom plus a
# base64 encode avoids depending on tools that may not exist in a slim image.
# $1 = exact number of characters required.
#
# Stripping the non-alphanumeric base64 characters (+ / = and newlines) is lossy,
# so asking for N bytes of randomness does NOT reliably yield N usable
# characters. Over-generating by 3x and then cutting guarantees the requested
# length exactly; the loop is a belt-and-braces guard in case a pathological
# draw still falls short.
random_secret() {
	_want="$1"
	_out=""
	while [ "${#_out}" -lt "$_want" ]; do
		if command -v openssl >/dev/null 2>&1; then
			_chunk="$(openssl rand -base64 "$((_want * 3))")"
		else
			_chunk="$(head -c "$((_want * 3))" /dev/urandom | base64)"
		fi
		_out="${_out}$(printf '%s' "$_chunk" | tr -d '\n=+/')"
	done
	printf '%s' "$_out" | cut -c1-"$_want"
}

# Django signs session cookies with SECRET_KEY. The guard in
# config/secret_guards.py requires at least 50 characters; 64 gives margin.
DJANGO_SECRET_KEY="$(random_secret 64)"
POSTGRES_PASSWORD="$(random_secret 32)"
RAG_AGENT_RO_PASSWORD="$(random_secret 32)"
STAFF_PASSWORD="$(random_secret 24)"

# --- create the file private, THEN write --------------------------------------
umask 077
: > "$OUT"
chmod 600 "$OUT"

cat > "$OUT" <<EOF
# Copyright (c) 2026 Yash Garad. All rights reserved.
#
# PRODUCTION environment. Generated $(date -u '+%Y-%m-%d %H:%M:%S UTC') by
# scripts/generate_secrets.sh.
#
#   * This file contains live credentials. It is covered by .gitignore and must
#     never be committed, emailed, or pasted into a chat or ticket.
#   * File permissions are 600 (owner read/write only). Keep them that way.
#   * Store a copy in the institute's password manager, not on a shared drive.
#
# THREE VALUES BELOW ARE PLACEHOLDERS YOU MUST EDIT BEFORE DEPLOYING.
# Each is marked with the token below. The backend refuses to start until they
# are replaced with your real server address.

# =============================================================================
# REQUIRED: set these to your actual server address
# =============================================================================

# The hostname or IP the server is reached at on the college network.
# Used for the TLS certificate and as the browser-facing origin.
# The name users type in the browser. For an INTERNET deployment this must be a
# real DNS name pointing at this server (e.g. rag.college.edu) — Caddy uses it
# to obtain the Let's Encrypt certificate.
SERVER_HOST=CHANGEME-SERVER-ADDRESS

# TLS mode. LEAVE EMPTY for a real Let's Encrypt certificate (internet).
# Set to "tls internal" ONLY for a LAN deployment with no public DNS name;
# every browser then warns until Caddy's CA is installed on each machine.
CADDY_TLS=

# Every hostname/IP Django will accept a request for, comma-separated.
# Must NOT be "*" — the backend rejects that outright.
DJANGO_ALLOWED_HOSTS=CHANGEME-SERVER-ADDRESS

# Same hosts, with the https:// scheme, comma-separated.
DJANGO_CSRF_TRUSTED_ORIGINS=https://CHANGEME-SERVER-ADDRESS

# =============================================================================
# Generated secrets - already set, no action needed
# =============================================================================

DJANGO_SECRET_KEY=$DJANGO_SECRET_KEY
POSTGRES_PASSWORD=$POSTGRES_PASSWORD
RAG_AGENT_RO_PASSWORD=$RAG_AGENT_RO_PASSWORD

# Bootstrap staff account created on first start. Phase 4 replaces this with
# per-user accounts; after that, this account should be disabled.
STAFF_USERNAME=admin
STAFF_PASSWORD=$STAFF_PASSWORD

# =============================================================================
# Production environment settings
# =============================================================================

DJANGO_ENV=production
DJANGO_DEBUG=false

# HSTS stays OFF until the Caddy root CA is installed on every client machine.
# Enabling it before then makes the certificate warning NON-BYPASSABLE and locks
# users out with no server-side undo. Ramp 3600 -> 86400 -> 31536000 afterwards.
DJANGO_HSTS_SECONDS=0

# The SPA and API share one origin behind Caddy, so no cross-origin access is
# needed. Leave empty unless you have a specific, justified reason.
DJANGO_CORS_ALLOWED_ORIGINS=

DJANGO_LOG_LEVEL=INFO

# Never load the demo dataset onto a server holding real student records.
SEED_DEMO_DATA=false

# =============================================================================
# Database and services
# =============================================================================

POSTGRES_DB=college_rag
POSTGRES_USER=postgres
POSTGRES_HOST=postgres
POSTGRES_PORT=5432

RAG_AGENT_RO_HOST=postgres
RAG_AGENT_RO_PORT=5432
RAG_AGENT_RO_DB=college_rag
RAG_AGENT_RO_USER=rag_agent_ro

QDRANT_URL=http://qdrant:6333
QDRANT_COLLECTION=college_docs

OLLAMA_BASE_URL=http://ollama:11434
EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_DIM=768
LLM_MODEL=qwen2.5:7b

SYNC_WORKER_POLL_INTERVAL_SECONDS=30

# =============================================================================
# Gunicorn (see backend/gunicorn.conf.py for the reasoning)
# =============================================================================

# ONE worker. This is a CORRECTNESS requirement, not a performance tuning knob.
#
# The DRF rate limiter and the LLM admission semaphore are both process-local
# (there is no Redis in this stack). With N workers there are N independent
# copies of each, so the effective limits become N x what is configured: the
# "10 questions per minute" cap silently becomes 30, and LLM_MAX_CONCURRENCY=1
# silently allows 3 concurrent generations on a CPU that can barely serve one.
#
# This file previously generated 3 here, which contradicted both
# backend/gunicorn.conf.py (defaults to 1) and docker-compose.prod.yml
# (${GUNICORN_WORKERS:-1}) — and, being an explicit value, quietly won over both.
#
# Raise this ONLY after moving the throttle and the semaphore to shared state.
GUNICORN_WORKERS=1
GUNICORN_THREADS=4
GUNICORN_TIMEOUT=300

# =============================================================================
# CPU inference tuning — these are NOT optional on a CPU-only server
# =============================================================================
# Both of the values below were arrived at by watching this system fail without
# them. Leaving them unset does not fall back to something merely slower; it
# falls back to something that visibly breaks for users.

# How long to wait for the model's FIRST token.
#
# The built-in default is 120s. A retrieval-heavy question sends roughly 2,000
# tokens of retrieved text for the model to read before it can emit anything,
# and on a CPU that read alone exceeds 120s. Every descriptive question then
# fails with "The AI service is temporarily unavailable" while nothing is
# actually wrong.
#
# Must stay BELOW GUNICORN_TIMEOUT (300) or gunicorn kills the worker before the
# HTTP client gives up. Raise both together, or neither.
# On a GPU server this can go back to the default — first tokens arrive in
# seconds there.
OLLAMA_READ_TIMEOUT=240

# THREAD COUNT. MUST AGREE WITH OLLAMA_CPU_LIMIT, AND THIS IS NOT A TUNING KNOB.
#
# A docker CPU limit is a QUOTA, not a core count. docker-compose.prod.yml caps
# ollama at OLLAMA_CPU_LIMIT (default 4.0), but `nproc` inside that container
# still reports every core on the host — 22 on the reference machine. So
# llama.cpp happily spawns 22 threads to share 4 CPUs' worth of quota, and they
# spend their time preempting each other.
#
# Measured on the production stack, same request, only this value changed:
#
#     num_thread=4     19.3 s wall,  3.73 tok/s
#     default (22)    201.9 s wall,  0.11 tok/s     <- 34x slower
#
# At the default EVERY request exceeded OLLAMA_READ_TIMEOUT and users got
# "The AI service is temporarily unavailable". Nothing was broken; the model was
# simply thrashing. This was invisible in development, which has no CPU limit at
# all and where the same setting is worth about 1.12x (docs/LATENCY.md, 18 Aug).
#
# If you raise OLLAMA_CPU_LIMIT, raise this to match. If you lower it, lower
# this. They must agree.
OLLAMA_NUM_THREAD=8

# Must equal OLLAMA_NUM_THREAD above. Raised from 4 to 8 on measured grounds
# (docs/SCALING.md, 22 Aug 2026): 4 sat BELOW the throughput knee and was the
# least reproducible point on the curve, with a 2.7x spread between identical
# runs. 8 is past the knee and the tightest of the post-knee points.
#
# On YOUR hardware the knee will be somewhere else. Run
# scripts/capacity_test.sh before trusting either number.
OLLAMA_CPU_LIMIT=8.0

# The model used for the fact-checking pass ONLY.
#
# Verification re-reads the question, the whole answer AND all the retrieved
# evidence, and cannot stream — so the entire verdict must be generated before
# anything returns. Measured on CPU: ~20s for a simple count, ~121s for a
# retrieval answer. With the 7b model it exceeded even a 240s timeout and every
# descriptive question came back unverified.
#
# qwen2.5:3b is downloaded by ollama-pull only if you list it in LLM_MODEL, so
# on a fresh server pull it once:
#     docker compose ... exec ollama ollama pull qwen2.5:3b
# Leave this blank to use LLM_MODEL for verification too (slower, and expect
# timeouts on long answers).
VERIFICATION_MODEL=qwen2.5:3b

# Inline fact-checking. ON by default; roughly +66% latency on a SQL answer and
# +86% on a retrieval answer. See backend/orchestrator/verification.py.
ENABLE_VERIFICATION=true

# LLM admission control. 1 is the honest default for CPU inference — the
# hardware cannot generate two answers at once, so admitting two only splits the
# same cores. A caller that waits longer than the queue timeout is told the
# assistant is busy rather than being left to hang.
LLM_MAX_CONCURRENCY=1
LLM_QUEUE_TIMEOUT=25

# =============================================================================
# Limits and retention
# =============================================================================
# Per-user question limit and per-IP login limit. Both genuinely per-key only
# because GUNICORN_WORKERS=1 (the counters are process-local).
ASK_RATE_LIMIT=10/min
LOGIN_RATE_LIMIT=10/min

# How long audit rows are kept. This is a GOVERNANCE value, not a technical one:
# the audit log records username, client IP, question text, the full answer and
# the generated SQL. Set it to whatever your data owner actually approved, and
# make sure the purge is scheduled — see DEPLOYMENT.md.
AUDIT_LOG_RETENTION_DAYS=90
EOF

chmod 600 "$OUT"

# --- report WITHOUT disclosing anything ---------------------------------------
echo "Created $OUT (permissions 600)."
echo
echo "Generated fresh values for:"
echo "    DJANGO_SECRET_KEY       (64 chars)"
echo "    POSTGRES_PASSWORD       (32 chars)"
echo "    RAG_AGENT_RO_PASSWORD   (32 chars)"
echo "    STAFF_PASSWORD          (24 chars)"
echo
echo "No secret has been printed. Open the file to read them."
echo
echo "NEXT — you must edit 3 placeholders before the backend will start:"
grep -n 'CHANGEME-SERVER-ADDRESS' "$OUT" | sed 's/^/    line /' || true
echo
echo "Then verify:"
echo "    grep -c CHANGEME-SERVER-ADDRESS $OUT   # must print 0"
echo "    git check-ignore -v $OUT  # must confirm it is ignored"
