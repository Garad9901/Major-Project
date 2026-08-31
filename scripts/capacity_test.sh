#!/bin/sh
# Copyright (c) 2026 Yash Garad. All rights reserved.
#
# WHAT THIS SERVER CAN ACTUALLY DO. Run it on your hardware before you promise
# anyone a number.
#
# ==============================================================================
# WHY THIS SHIPS INSTEAD OF A FIGURE
# ==============================================================================
# The obvious thing to put in a datasheet is "serves N concurrent users". We
# will not, because we cannot honestly measure it for your server.
#
# This system was developed on a laptop, inside a Docker VM, on an Intel Core
# Ultra 9 185H — a HYBRID CPU with 6 performance cores, 8 efficiency cores and 2
# low-power cores. Inside the VM that asymmetry is invisible: it presents as a
# uniform 11 cores x 2 threads, and the hypervisor decides which physical core
# each virtual one lands on, differently from one run to the next. A Docker
# `cpus:` limit makes it worse — it is a scheduling QUOTA, not an affinity, so
# inference threads migrate across whatever the host happens to offer.
#
# So a figure from that machine describes a laptop VM on a hybrid CPU. Your
# server is very likely a homogeneous Xeon or EPYC, where the effect that
# dominates our curve does not exist at all. Publishing our number as your
# specification would be a fabrication with a decimal point on it.
#
# What transfers is the METHOD. Run this; the number it prints is yours.
#
# ==============================================================================
# WHAT THE NUMBER MEANS — read this before quoting it
# ==============================================================================
# LLM_MAX_CONCURRENCY defaults to 1, because CPU inference cannot genuinely run
# two generations at once; admitting two only splits the same cores. So capacity
# here is NOT parallelism. It is QUEUEING:
#
#     users served ~= LLM_QUEUE_TIMEOUT / mean_answer_time
#
# A user who waits longer than LLM_QUEUE_TIMEOUT is told the assistant is busy
# rather than being left hanging. Two consequences worth being explicit about:
#
#   * CPU speed enters only through mean_answer_time. Faster cores raise
#     capacity by shortening answers, not by serving more at once.
#   * RAISING LLM_QUEUE_TIMEOUT RAISES THE NUMBER WITHOUT IMPROVING ANYTHING.
#     It just makes people wait longer before being turned away. The shipped
#     default of 25s assumes a student will tolerate about half a minute of
#     apparent nothing before giving up. That is a guess about YOUR users, not
#     a technical constant — if your users are staff at desks rather than
#     students on phones, it may be far too low.
#
# That is why this reports concurrency, mean answer time AND queue timeout
# together. A capacity figure without its inputs is not a specification.
#
# ==============================================================================
# TWO LOAD SHAPES, AND YOU NEED BOTH
# ==============================================================================
#   PESSIMAL   every user asks a DIFFERENT question. Nothing hits the response
#              cache, nothing coalesces. This is the honest worst case and the
#              only figure safe to guarantee.
#
#   REALISTIC  questions repeat, which is what a college actually produces —
#              during registration or results week most traffic is the same
#              handful of questions. The semantic cache and the request
#              coalescer exist for exactly that, and a distinct-only test hides
#              the thing they were built to do.
#
# The repetition rate for the realistic run is an ASSUMPTION you are setting,
# not a measurement. It is printed with the result so nobody mistakes it for one.
#
# Usage:
#   sh scripts/capacity_test.sh
#   USERS=50 REPETITION=70 sh scripts/capacity_test.sh
#   USERS=20 SERVER_URL=https://rag.college.edu sh scripts/capacity_test.sh

set -eu

USERS="${USERS:-20}"
REPETITION="${REPETITION:-70}"        # percent of realistic traffic that repeats
WARMUP_WAIT="${WARMUP_WAIT:-900}"

if [ -f .env.production ]; then
	ENV_FILE=.env.production
elif [ -f .env ]; then
	ENV_FILE=.env
else
	echo "ERROR: no .env.production or .env found. Run this from the project root." >&2
	exit 1
fi

_get() { grep -E "^$1=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '\r'; }

SERVER_HOST="$(_get SERVER_HOST)"
SERVER_URL="${SERVER_URL:-https://${SERVER_HOST:-localhost}}"
STAFF_USERNAME="$(_get STAFF_USERNAME)"
STAFF_PASSWORD="$(_get STAFF_PASSWORD)"
QUEUE_TIMEOUT="$(_get LLM_QUEUE_TIMEOUT)"; QUEUE_TIMEOUT="${QUEUE_TIMEOUT:-25}"
MAX_CONC="$(_get LLM_MAX_CONCURRENCY)"; MAX_CONC="${MAX_CONC:-1}"

echo "============================================================="
echo " CAPACITY TEST"
echo "============================================================="
echo " Server            : $SERVER_URL"
echo " Simulated users   : $USERS (arriving together)"
echo " Queue timeout     : ${QUEUE_TIMEOUT}s   (LLM_QUEUE_TIMEOUT)"
echo " Max concurrency   : $MAX_CONC     (LLM_MAX_CONCURRENCY)"
echo " Repetition assumed: ${REPETITION}%  (realistic run only — YOUR assumption)"
echo

# ------------------------------------------------------------------------------
# 0. The system must be READY, not merely up.
#
# /api/health/ returns 503 with "warming" until every model is resident. Running
# a capacity test during warm-up measures model loading, which is a one-off cost
# at deployment and has nothing to do with capacity.
# ------------------------------------------------------------------------------
printf 'Waiting for the assistant to be ready (models resident)'
WAITED=0
while [ "$WAITED" -lt "$WARMUP_WAIT" ]; do
	CODE=$(curl -sk -o /dev/null -w '%{http_code}' "$SERVER_URL/api/health/" || echo 000)
	[ "$CODE" = "200" ] && break
	printf '.'
	sleep 10
	WAITED=$((WAITED + 10))
done
echo
if [ "$CODE" != "200" ]; then
	echo "ERROR: still not ready after ${WARMUP_WAIT}s. Current health:" >&2
	curl -sk "$SERVER_URL/api/health/" >&2; echo >&2
	echo "On CPU-only hardware the first load can take 15+ minutes. Raise WARMUP_WAIT." >&2
	exit 1
fi
echo "Ready."
echo

# ------------------------------------------------------------------------------
# 1. Sign in once and reuse the cookie jar for every simulated user.
#
# The point is to load the ANSWER path, not the login path.
# ------------------------------------------------------------------------------
JAR=$(mktemp)
curl -sk -c "$JAR" -b "$JAR" "$SERVER_URL/api/auth/csrf/" >/dev/null
CSRF=$(grep csrftoken "$JAR" | awk '{print $7}')
LOGIN=$(curl -sk -c "$JAR" -b "$JAR" -o /dev/null -w '%{http_code}' \
	-X POST "$SERVER_URL/api/auth/login/" -H "Content-Type: application/json" \
	-H "X-CSRFToken: $CSRF" -H "Referer: $SERVER_URL/" \
	-d "{\"username\":\"$STAFF_USERNAME\",\"password\":\"$STAFF_PASSWORD\"}")
if [ "$LOGIN" != "200" ]; then
	echo "ERROR: could not sign in (HTTP $LOGIN)." >&2
	echo "If this account still has must_change_password set, change it first." >&2
	rm -f "$JAR"; exit 1
fi
CSRF=$(grep csrftoken "$JAR" | awk '{print $7}')

ask_one() {
	# ask_one <question> <outfile> <bypass_cache: true|false>
	S=$(date +%s)
	CODE=$(curl -sk -o "$2.body" -w '%{http_code}' --max-time 600 \
		-b "$JAR" -X POST "$SERVER_URL/api/ask/" \
		-H "Content-Type: application/json" -H "X-CSRFToken: $CSRF" \
		-H "Referer: $SERVER_URL/" \
		-d "{\"question\":$1,\"regenerate\":$3}" 2>/dev/null || echo 000)
	E=$(date +%s)
	# CLASSIFY ON THE `done` EVENT, NOT ON THE STRING "error".
	#
	# This used to test `grep -q '"error"'`, which matched EVERY SUCCESSFUL
	# ANSWER. The done event carries the per-stage timing profile, and each
	# stage records its error field — so a perfectly good response contains
	#
	#     "error": null
	#
	# twice. Run against a working system this script reported 0 served and
	# every user failed. It was the measuring instrument that was broken, which
	# is the worst place for a bug of this kind: a buyer would have concluded
	# their server could not answer anything.
	#
	# The stream ends with `event: done` only when an answer completed. That is
	# the signal.
	if grep -q '^event: done' "$2.body" 2>/dev/null; then R=ok
	elif grep -qi 'busy' "$2.body" 2>/dev/null; then R=busy
	elif [ "$CODE" != "200" ]; then R=http$CODE
	else R=error
	fi
	echo "$R $((E - S))" > "$2"
	rm -f "$2.body"
}

# ------------------------------------------------------------------------------
# THE DISTINCT-QUESTION POOL — these have to be REAL QUESTIONS.
#
# This previously generated "How many faculty are in department number N of the
# survey?" for each user. That is not a question this dataset can answer:
# `faculty_development.department` holds plain text ('Engineering', 'Computer
# Science') and there is no department NUMBER anywhere in the schema.
#
# The model duly invented a `department_id` column, the SQL errored, and
# verification escalated to its slowest LLM path (sql errored -> needs
# judgement). Answers took 180-200s instead of ~30s. So the pessimal run — THE
# FIGURE THIS SCRIPT TELLS YOU TO GUARANTEE — was measuring the invalid-question
# path rather than capacity, and understating the server several-fold.
#
# These are genuinely different, genuinely answerable questions across the
# survey's real dimensions. Nothing coalesces, and every one exercises the path
# a real user takes.
# ------------------------------------------------------------------------------
build_question_pool() {
	POOL=""
	for D in Engineering "Computer Science" Science Management Education \
	         "Arts and Humanities" "Social Science" Medicine; do
		POOL="$POOL|How many faculty are in the $D department?"
	done
	for R in Professor "Associate Professor" "Assistant Professor" Lecturer; do
		POOL="$POOL|How many faculty hold the $R rank?"
	done
	for L in Expert Advanced Intermediate Basic; do
		POOL="$POOL|How many faculty have a competency level of $L?"
	done
	for U in Public Private Deemed; do
		POOL="$POOL|How many faculty records come from $U universities?"
	done
	# Cross department x rank, so a USERS=50 run still gets 50 genuinely
	# distinct questions rather than wrapping around a short pool.
	for D in Engineering "Computer Science" Science Management Education \
	         "Arts and Humanities" "Social Science" Medicine; do
		for R in Professor "Associate Professor" "Assistant Professor" Lecturer; do
			POOL="$POOL|How many $R faculty are in the $D department?"
		done
	done
	POOL_SIZE=$(printf '%s' "$POOL" | tr '|' '
' | grep -c .)
}
build_question_pool

if [ "$USERS" -gt "$POOL_SIZE" ]; then
	echo "ERROR: USERS=$USERS exceeds the $POOL_SIZE distinct questions available." >&2
	echo "       Questions would have to repeat, and repeated questions COALESCE:" >&2
	echo "       the pessimal run would quietly become a partly-realistic one and" >&2
	echo "       OVERSTATE capacity. Lower USERS, or extend build_question_pool." >&2
	exit 1
fi

run_wave() {
	# run_wave <label> <distinct|repeating>
	LABEL="$1"; SHAPE="$2"
	WORK=$(mktemp -d)
	I=0
	while [ "$I" -lt "$USERS" ]; do
		DISTINCT_Q=$(printf '%s' "$POOL" | cut -d'|' -f$((I + 2)))
		if [ "$SHAPE" = "distinct" ]; then
			Q="\"$DISTINCT_Q\""
			# BYPASS THE RESPONSE CACHE ON THE PESSIMAL RUN.
			#
			# "Pessimal" is DEFINED as nothing hitting the cache. On a first
			# run distinct questions miss anyway — but on the SECOND run of
			# this script they are all cached, and the pessimal figure comes
			# back inflated by the very mechanism the shape excludes. We saw
			# exactly that: a repeat run reported a 7s mean, which was the
			# cache answering rather than the server working.
			#
			# The realistic run deliberately does NOT bypass: there the cache
			# and the coalescer are the things under test.
			BYPASS=true
		else
			# REPETITION% of users ask the same question; the rest differ.
			if [ "$(( (I * 100 / USERS) ))" -lt "$REPETITION" ]; then
				Q='"How many faculty are in the Computer Science department?"'
			else
				Q="\"$DISTINCT_Q\""
			fi
			BYPASS=false
		fi
		ask_one "$Q" "$WORK/$I" "$BYPASS" &
		I=$((I + 1))
	done
	wait

	OK=0; BUSY=0; ERR=0; TOTAL_T=0
	for F in "$WORK"/*; do
		case "$F" in *.body) continue ;; esac
		# shellcheck disable=SC2046  # word splitting is the point: fields -> $1..$4
		set -- $(cat "$F")
		case "$1" in
			ok)   OK=$((OK + 1));   TOTAL_T=$((TOTAL_T + $2)) ;;
			busy) BUSY=$((BUSY + 1)) ;;
			*)    ERR=$((ERR + 1)) ;;
		esac
	done
	MEAN=0; [ "$OK" -gt 0 ] && MEAN=$((TOTAL_T / OK))

	# SPREAD, NOT JUST A MEAN.
	#
	# A mean over a wide distribution is not a point estimate. We measured a
	# 2.7x spread between identical runs on our own development hardware, where
	# a median of three samples turned out to be whichever mode happened to win
	# two draws — it looked like a stable figure and was a coin flip.
	#
	# So the rule, and it now travels with the script: WHERE SPREAD EXCEEDS
	# ~1.5x, DO NOT QUOTE THE MEAN. Take more samples or quote the range.
	FASTEST=0; SLOWEST=0
	for F in "$WORK"/*; do
		case "$F" in *.body) continue ;; esac
		# shellcheck disable=SC2046  # word splitting is the point: fields -> $1..$4
		set -- $(cat "$F")
		[ "$1" = "ok" ] || continue
		[ "$FASTEST" -eq 0 ] || [ "$2" -lt "$FASTEST" ] && FASTEST=$2
		[ "$2" -gt "$SLOWEST" ] && SLOWEST=$2
	done
	rm -rf "$WORK"

	# A MINIMUM SAMPLE COUNT, INDEPENDENT OF OBSERVED SPREAD.
	#
	# The spread check below is ONE-SIDED: it fires only when variance is
	# actually observed. A short run that happens to miss a rare slow case
	# reports a tight range and passes in silence — which is exactly the trap we
	# fell into ourselves.
	#
	# Measuring our own hardware, one allocation produced a slow outlier in
	# 1 of 8 samples. At that rate THREE samples miss it 67% of the time —
	# (7/8)^3 — so a clean-looking three-sample range is not evidence of
	# stability, it is the absence of a measurement. We had shipped a default
	# chosen on exactly that basis.
	#
	# So: below MIN_SAMPLES the figure is refused rather than qualified. A
	# warning next to a number still leaves a number to quote.
	MIN_SAMPLES="${MIN_SAMPLES:-8}"
	UNDERSAMPLED=""
	if [ "$OK" -lt "$MIN_SAMPLES" ]; then
		UNDERSAMPLED="yes"
	fi

	SPREAD_NOTE=""
	if [ "$FASTEST" -gt 0 ] && [ "$((SLOWEST * 10 / FASTEST))" -gt 15 ]; then
		SPREAD_NOTE="  <-- SPREAD EXCEEDS 1.5x; the mean is NOT a reliable figure"
	fi

	echo "  $LABEL"
	echo "    answered      : $OK / $USERS"
	echo "    turned away   : $BUSY  (told the assistant is busy — correct behaviour)"
	echo "    failed        : $ERR"
	echo "    mean answer   : ${MEAN}s (over the answered ones)"
	echo "    range         : ${FASTEST}s - ${SLOWEST}s${SPREAD_NOTE}"
	if [ -n "$UNDERSAMPLED" ]; then
		echo
		echo "    *** NOT A PUBLISHABLE FIGURE: only $OK answers completed, and this"
		echo "        script will not present a capacity number below $MIN_SAMPLES."
		echo
		echo "        A tight range over a handful of samples is not evidence of"
		echo "        stability — it is the absence of a measurement. On our own"
		echo "        hardware one configuration produced a slow outlier in 1 of 8"
		echo "        samples; three samples would have missed it 67% of the time"
		echo "        and reported a clean range. We shipped a default on exactly"
		echo "        that mistake."
		echo
		echo "        Re-run with USERS=$MIN_SAMPLES or more."
	elif [ -n "$SPREAD_NOTE" ]; then
		echo "                    Re-run with more USERS, or quote the range rather"
		echo "                    than the mean. A wide spread usually means the"
		echo "                    machine is contended or thermally throttling."
	fi
	echo
	# stash for the summary
	echo "$OK $BUSY $ERR $MEAN" > "/tmp/capacity_$SHAPE"
}

echo "-------------------------------------------------------------"
echo " RUN 1 of 2 — PESSIMAL (every user asks something different)"
echo "-------------------------------------------------------------"
run_wave "all-distinct questions" distinct

echo "-------------------------------------------------------------"
echo " RUN 2 of 2 — REALISTIC (${REPETITION}% of users ask the same thing)"
echo "-------------------------------------------------------------"
run_wave "${REPETITION}% repeated questions" repeating

rm -f "$JAR"

# shellcheck disable=SC2046  # word splitting is the point: fields -> $1..$4
set -- $(cat /tmp/capacity_distinct); D_OK=$1; D_MEAN=$4
# shellcheck disable=SC2046  # word splitting is the point: fields -> $1..$4
set -- $(cat /tmp/capacity_repeating); R_OK=$1; R_MEAN=$4
rm -f /tmp/capacity_distinct /tmp/capacity_repeating

CPUINFO="$(grep -m1 'model name' /proc/cpuinfo 2>/dev/null | cut -d: -f2- | sed 's/^ *//')"
CORES="$(nproc 2>/dev/null || echo '?')"
RAMGB="$(awk '/^MemTotal:/ {printf "%d", $2/1024/1024}' /proc/meminfo 2>/dev/null || echo '?')"

echo "============================================================="
echo " YOUR CAPACITY FIGURE"
echo "============================================================="
echo
echo " On ${CPUINFO:-this server} (${CORES} logical CPUs, ${RAMGB} GB RAM),"
echo " with LLM_MAX_CONCURRENCY=$MAX_CONC and LLM_QUEUE_TIMEOUT=${QUEUE_TIMEOUT}s:"
echo
echo "   * assuming ${REPETITION}% repeated questions, it serves ${R_OK} of ${USERS}"
echo "     concurrent users at a mean answer time of ${R_MEAN}s"
echo "   * with ALL-DISTINCT questions the figure is ${D_OK} of ${USERS},"
echo "     at ${D_MEAN}s"
echo
echo " Guarantee the all-distinct figure. Expect the other one in practice."
echo
echo " The repetition rate is an assumption you set, not something measured."
echo " Re-run with REPETITION=<n> to model your own traffic."
echo
echo " To serve more users: shorten the answer (faster CPU, or a smaller"
echo " SYNTHESIS_MODEL) — not more cores. With LLM_MAX_CONCURRENCY=1 capacity"
echo " is queueing, so it moves with answer TIME. Raising LLM_QUEUE_TIMEOUT"
echo " raises this number without making anything faster; it only makes people"
echo " wait longer before being turned away."
echo "============================================================="
