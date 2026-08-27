#!/bin/sh
# Copyright (c) 2026 Yash Garad. All rights reserved.
#
# THE MODELS THIS DEPLOYMENT NEEDS ON DISK, one per line, deduplicated.
#
# ==============================================================================
# WHY THIS IS A FILE AND NOT A LIST IN docker-compose.yml
# ==============================================================================
# ollama-pull used to loop over a hand-written list of three env vars:
#
#     for model in "$EMBEDDING_MODEL" "$LLM_MODEL" "$VERIFICATION_MODEL"
#
# The application reads SIX. router_agent/llm_client.py reads ROUTER_MODEL,
# which has its OWN default (qwen2.5:3b) rather than falling back to LLM_MODEL,
# and synthesis_agent and sql_agent each read their own override. None of those
# three were in the loop.
#
# It worked only by coincidence: VERIFICATION_MODEL happened to be set to
# qwen2.5:3b, the same value ROUTER_MODEL defaults to. Measured, with the
# compose file's exact enumeration:
#
#   VERIFICATION_MODEL=qwen2.5:3b  -> pulls nomic-embed-text qwen2.5:7b qwen2.5:3b
#                                     router covered BY COINCIDENCE
#   VERIFICATION_MODEL=<blank>     -> pulls nomic-embed-text qwen2.5:7b
#                                     ROUTER MODEL NEVER PULLED
#   VERIFICATION_MODEL=llama3.2:1b -> pulls nomic-embed-text qwen2.5:7b llama3.2:1b
#                                     ROUTER MODEL NEVER PULLED
#
# and .env.production explicitly tells operators they may leave VERIFICATION_MODEL
# blank. The consequence is not a slow first question, it is a permanent one:
# common/ollama.py counts ROUTER_MODEL as required-resident, so /api/health/
# reports "loading qwen2.5:3b" and returns 503 forever. Measured against the
# live server with a model ollama-pull would never fetch:
#
#     is_ready([...,'mistral:7b'])  ->  (False, 'loading mistral:7b')
#
# So the list lives in ONE place that both the puller and the readiness check
# are tested against. backend/common/test_model_config.py fails if they ever disagree.
#
# ==============================================================================
# WHAT BLANK MEANS, because the code and the documentation disagreed
# ==============================================================================
# .env.production says of VERIFICATION_MODEL: "Leave this blank to use LLM_MODEL
# for verification too." The code was
#
#     os.getenv("VERIFICATION_MODEL", os.getenv("LLM_MODEL", "qwen2.5:7b"))
#
# and os.getenv returns "" for a variable that is SET BUT EMPTY — a default only
# applies when the name is absent. So following that instruction produced an
# EMPTY model name, not LLM_MODEL. Verified:
#
#     VERIFICATION_MODEL= -> resolved '' (documented: qwen2.5:7b)
#
# Here and in the application, BLANK AND UNSET BOTH MEAN "use the fallback".
#
# Usage:
#   sh backend/scripts/required_models.sh           # every model needed on disk
#   sh backend/scripts/required_models.sh --chat    # excludes embedding models, which
#                                           # take no chat request and so are
#                                           # neither preloaded nor expected in
#                                           # `ollama ps`

set -eu

# Blank OR unset falls back. See the note above.
_or() {
	if [ -n "${1:-}" ]; then
		printf '%s' "$1"
	else
		printf '%s' "$2"
	fi
}

LLM="$(_or "${LLM_MODEL:-}" "qwen2.5:7b")"

EMBEDDING="$(_or "${EMBEDDING_MODEL:-}" "nomic-embed-text")"

# ROUTER_MODEL IS THE ONE THAT DIVERGED. It does not fall back to LLM_MODEL —
# routing is a cheap four-way classification and deliberately defaults to a
# SMALLER model, so on a default deployment this is a second model that must be
# on disk and nothing was fetching it.
ROUTER="$(_or "${ROUTER_MODEL:-}" "qwen2.5:3b")"

# These three default to LLM_MODEL, so they add nothing unless overridden.
VERIFICATION="$(_or "${VERIFICATION_MODEL:-}" "$LLM")"
SYNTHESIS="$(_or "${SYNTHESIS_MODEL:-}" "$LLM")"
SQL_AGENT="$(_or "${SQL_AGENT_MODEL:-}" "$LLM")"

CHAT_ONLY=""
[ "${1:-}" = "--chat" ] && CHAT_ONLY=1

SEEN=""
for MODEL in "$EMBEDDING" "$LLM" "$ROUTER" "$VERIFICATION" "$SYNTHESIS" "$SQL_AGENT"; do
	[ -n "$MODEL" ] || continue

	if [ -n "$CHAT_ONLY" ]; then
		case "$MODEL" in
			*embed*) continue ;;
		esac
	fi

	# Deduplicate. Several vars resolving to LLM_MODEL is the NORMAL case, and
	# re-pulling is merely wasteful, but a duplicate would also be reported
	# twice by the residency check and read as two problems.
	case " $SEEN " in
		*" $MODEL "*) continue ;;
	esac
	SEEN="$SEEN $MODEL"

	printf '%s\n' "$MODEL"
done
