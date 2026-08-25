#!/bin/sh
# Copyright (c) 2026 Yash Garad. All rights reserved.
#
# FUNCTIONAL TEST FOR THE DERIVED CPU ALLOCATION.
#
# scripts/generate_secrets.sh no longer ships a tuned literal for
# OLLAMA_CPU_LIMIT; it derives one from the machine it runs on. That derivation
# is the thing a buyer's deployment depends on for inference not to collapse
# (a mismatch between the quota and the thread count measured 34x slower), and
# it runs exactly once, on a machine we will never see. So it needs a test.
#
# The function reads the machine through `nproc` and `lscpu`. This test puts
# stubs for both ahead of the real ones on PATH and asserts the derived value
# for a range of machine shapes — including shapes we cannot obtain: a 64-core
# dual-socket Xeon, a machine with no lscpu at all, and a box too small to run
# this system.
#
# IT EXTRACTS THE FUNCTION FROM THE SHIPPED SCRIPT rather than restating it, so
# the test cannot drift away from the code it is testing.
#
# Usage:  sh scripts/test_generate_secrets.sh

set -eu

SCRIPT="$(dirname "$0")/generate_secrets.sh"
[ -f "$SCRIPT" ] || { echo "cannot find $SCRIPT" >&2; exit 1; }

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

# Pull just the function out of the shipped script.
sed -n '/^derive_cpu_allocation() {/,/^}/p' "$SCRIPT" > "$WORK/derive.inc"
if [ ! -s "$WORK/derive.inc" ]; then
	echo "FAIL: could not extract derive_cpu_allocation from $SCRIPT" >&2
	echo "      (was it renamed? this test is now testing nothing)" >&2
	exit 1
fi

PASS=0
FAIL=0

# check <description> <logical> <cores_per_socket|-> <sockets|-> <expected> <expect_warning:yes|no>
check() {
	DESC="$1"; LOGICAL="$2"; CPS="$3"; SOCKETS="$4"; EXPECT="$5"; EXPECT_WARN="$6"

	BIN="$WORK/bin"; rm -rf "$BIN"; mkdir -p "$BIN"

	printf '#!/bin/sh\necho %s\n' "$LOGICAL" > "$BIN/nproc"
	chmod +x "$BIN/nproc"

	if [ "$CPS" = "-" ]; then
		# THE "lscpu TELLS US NOTHING" PATH.
		#
		# This stub exists but reports no topology, which is what a container
		# with a stripped util-linux, or a kernel that does not expose the
		# fields, actually looks like. The function then falls through to
		#
		#     [ -n "$_physical" ] || _physical=$((_logical / 2))
		#
		# BEING PRECISE ABOUT WHAT THIS DOES AND DOES NOT COVER: a machine
		# with no lscpu BINARY takes the same branch by a different route
		# (`command -v` fails rather than the fields being empty). That route
		# is not exercised here, because PATH has to keep the real awk the
		# function depends on, and a real lscpu would then leak in with it.
		# The arithmetic being checked is identical on both routes; the
		# untested part is two lines of `command -v`.
		printf "#!/bin/sh
exit 0
" > "$BIN/lscpu"
		chmod +x "$BIN/lscpu"
	else
		cat > "$BIN/lscpu" <<LSCPU
#!/bin/sh
echo "Architecture:        x86_64"
echo "CPU(s):              $LOGICAL"
echo "Core(s) per socket:  $CPS"
echo "Socket(s):           $SOCKETS"
LSCPU
		chmod +x "$BIN/lscpu"
	fi

	# Stubs FIRST, so they shadow anything real, while the function keeps the
	# awk it depends on. Every case installs an lscpu stub, so the real one
	# is shadowed in all of them.
	RESULT=$(PATH="$BIN:$PATH" /bin/sh -c '
		set -eu
		DERIVE_WARNING=""
		. "$1"
		derive_cpu_allocation
		echo "$CPU_ALLOCATION|$CPU_DETECTED|$DERIVE_WARNING"
	' _ "$WORK/derive.inc")

	GOT=$(printf '%s' "$RESULT" | cut -d'|' -f1)
	DETECTED=$(printf '%s' "$RESULT" | cut -d'|' -f2)
	WARN=$(printf '%s' "$RESULT" | cut -d'|' -f3)

	GOT_WARN=no
	[ -n "$WARN" ] && GOT_WARN=yes

	if [ "$GOT" = "$EXPECT" ] && [ "$GOT_WARN" = "$EXPECT_WARN" ]; then
		PASS=$((PASS + 1))
		printf '  ok    %-46s -> %-3s (%s)\n' "$DESC" "$GOT" "$DETECTED"
	else
		FAIL=$((FAIL + 1))
		printf '  FAIL  %-46s -> %s (warning=%s), expected %s (warning=%s)\n' \
			"$DESC" "$GOT" "$GOT_WARN" "$EXPECT" "$EXPECT_WARN"
	fi
}

echo "Deriving OLLAMA_CPU_LIMIT for machine shapes we cannot obtain:"
echo

# --- server hardware, which is what a buyer actually has ----------------------
check "dual-socket Xeon, 16c/socket, SMT"      64 16 2 32 no
check "single-socket EPYC, 32c, SMT"           64 32 1 32 no
check "modest 1U server, 8c, SMT"              16  8 1  8 no
check "6-core server, SMT"                     12  6 1  6 no

# --- the ceiling binds before the core count does -----------------------------
# 8 physical cores but no SMT: 8 logical total, minus 2 for the rest of the
# stack = 6. The rule wants 8; it cannot have it.
check "8 cores, NO SMT (ceiling binds)"         8  8 1  6 no

# --- odd allocations are rounded down -----------------------------------------
# The single odd allocation measured (11) collapsed generation to 3.04 tok/s in
# 8 of 8 samples. Rounding down is free, so it is taken.
check "5 physical cores (odd -> even)"         10  5 1  4 no

# --- THE REFERENCE MACHINE, and the documented worked example -----------------
# The Docker VM on the 185H laptop reports a synthetic 11 physical / 22 logical.
# The formula lands on 10. Measurement preferred 12. docs/SCALING.md publishes
# this disagreement deliberately: derive a starting point, then MEASURE it.
check "reference laptop VM (formula says 10)"  22 11 1 10 no

# --- topology unavailable: assume SMT and halve --------------------------------
check "lscpu reports nothing, 8 logical"        8  -  -  4 no
check "lscpu reports nothing, 32 logical"      32  -  - 16 no

# --- machines too small for this system, which must WARN, not fail silently ---
check "4 logical CPUs (below the floor)"        4  2 1  4 yes
check "2 logical CPUs (below the floor)"        2  1 1  4 yes
check "1 logical CPU (degenerate)"              1  1 1  4 yes

echo
echo "-------------------------------------------------------------"
echo " $PASS passed, $FAIL failed"
echo "-------------------------------------------------------------"

if [ "$FAIL" -ne 0 ]; then
	exit 1
fi

# --- the invariant that actually matters --------------------------------------
# OLLAMA_NUM_THREAD and OLLAMA_CPU_LIMIT must agree. They are written from the
# same variable, but a future edit could easily set one and not the other, and
# the failure mode is a 34x slowdown that looks like slow hardware rather than
# a misconfiguration. verify_deployment.sh checks this at deploy time; this
# checks the generator that produces it.
if ! grep -q '^OLLAMA_NUM_THREAD=\$CPU_ALLOCATION$' "$SCRIPT"; then
	echo "FAIL: OLLAMA_NUM_THREAD is no longer written from \$CPU_ALLOCATION." >&2
	exit 1
fi
if ! grep -q '^OLLAMA_CPU_LIMIT=\$CPU_ALLOCATION\.0$' "$SCRIPT"; then
	echo "FAIL: OLLAMA_CPU_LIMIT is no longer written from \$CPU_ALLOCATION." >&2
	exit 1
fi
echo "OLLAMA_NUM_THREAD and OLLAMA_CPU_LIMIT are both written from one value."
