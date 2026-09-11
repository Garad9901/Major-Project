# Copyright (c) 2026 Yash Garad. All rights reserved.

"""Gunicorn configuration for the production backend.

WHY THESE NUMBERS
-----------------
The usual "(2 x CPU) + 1" rule sizes workers for CPU-bound request handling.
That rule is actively wrong here, and following it would make the system worse.

The bottleneck in this application is not Django and not the CPU count of the
web container — it is Ollama. Local language-model inference on CPU serialises:
Ollama processes roughly one generation at a time, and a second concurrent
generation does not run twice as fast, it makes both slower while consuming the
same cores Django needs. Spawning sixteen Gunicorn workers would not increase
throughput by one request; it would queue sixteen requests at Ollama, multiply
memory use by sixteen, and starve Ollama of the CPU it needs to answer any of
them.

So workers are sized for *how many users can be waiting concurrently without
exhausting memory*, not for parallel compute.

  worker_class = gthread
      Requests here are I/O-bound in the extreme: a worker submits a prompt to
      Ollama and then waits 20-90 seconds for tokens, holding an open SSE
      connection the whole time. Threads park on that wait cheaply. Sync workers
      would burn one whole process per waiting user. gevent would be cheaper
      still, but it requires monkey-patching psycopg2 and the Ollama HTTP client,
      which is a correctness risk not worth taking for this concurrency level.

  workers = 1 (override with GUNICORN_WORKERS)
      REVISED FROM 3. Not a performance decision — a correctness one.

      Two limits in this application are enforced with PROCESS-LOCAL state:
      DRF's throttle cache (per-user request rate) and the LLM admission
      semaphore in orchestrator/concurrency.py. Neither is shared between
      processes without Redis, which this deployment deliberately does not run.

      With N workers, both limits silently become N times looser: a user gets
      N x 10 requests/minute by landing on different workers, and N questions
      enter the LLM pipeline concurrently against hardware that can serve one.
      The limits would still LOOK right in the config while being wrong in
      practice, which is the worst kind of wrong.

      One worker makes process-local and global the same thing.

      THE COST, stated plainly: no in-process redundancy. If the worker wedges,
      the service is down until Docker notices. That is mitigated by the
      container healthcheck plus restart: always, and it is a real trade-off
      rather than a free win. Introduce Redis and this becomes safe to raise.

  threads = 24 (override with GUNICORN_THREADS)
      RAISED FROM 4. The original reasoning — extra threads let a waiting
      request be told "busy" politely rather than refused at the socket — is
      still right, and is why this is larger than LLM_MAX_CONCURRENCY (1).
      What changed is that threads became the binding constraint on the
      DETERMINISTIC path, which needs no model at all.

      Arithmetic, from measured numbers:

          fast path end to end       ~200 ms  (measured 177-368 ms)
          4 threads                  4 / 0.2 = 20 requests/second
          100 simultaneous arrivals  100 / 20 = 5.0 s to drain, p95 ~4.75 s

      against a target of p95 under 1 second. Draining 100 requests inside a
      second at 200 ms each needs ~20-24 threads, so 24.

      This is sound only because the fast path is I/O-BOUND — one indexed
      aggregate and a socket write — so the threads park rather than compete for
      the GIL. It would not be sound for CPU-bound work.

      RAISING THIS ALONE MOVES THE BOTTLENECK RATHER THAN REMOVING IT, which is
      why three things moved together in one commit:
        * threads                        4  -> 24  (here)
        * RAG_AGENT_RO_POOL_MAX          8  -> 24  (sql_agent/db.py)
        * rag_agent_ro CONNECTION LIMIT  10 -> 32  (db/sql/create_rag_agent_ro.sql)

      The third is not optional. docs/SCALING.md records an outage caused by
      CONN_MAX_AGE=60 holding one persistent connection per thread until
      Postgres refused with "too many clients already". 24 threads against a
      role limit of 10 reproduces that incident exactly.

      Budget check on the reference machine: max_connections=100, of which
      ~24 Django (app user, CONN_MAX_AGE=60) + up to 24 rag_agent_ro + 1 sync
      worker + operator headroom. Measured 7 in use before the change.

TIMEOUTS
--------
Default Gunicorn timeout is 30 seconds, which would sever every single answer
this application produces — measured response times on this stack are 19-22
seconds warm and up to 87 seconds on a cold model. Timeouts below are set from
those measurements with headroom, not from habit.
"""

import os

# --- socket ------------------------------------------------------------------
bind = os.getenv("GUNICORN_BIND", "0.0.0.0:8000")

# --- worker model ------------------------------------------------------------
workers = int(os.getenv("GUNICORN_WORKERS", "1"))
threads = int(os.getenv("GUNICORN_THREADS", "24"))
worker_class = "gthread"

# --- timeouts ----------------------------------------------------------------
# Must exceed the slowest realistic answer. A cold model took 87s on this stack;
# 300s leaves room for a cold start under load without hanging a client forever.
# The application-level timeout added in Phase 5 will cut in below this, so this
# value is the backstop, not the primary control.
timeout = int(os.getenv("GUNICORN_TIMEOUT", "300"))

# On shutdown, let in-flight answers finish streaming rather than truncating a
# user's response mid-sentence.
graceful_timeout = int(os.getenv("GUNICORN_GRACEFUL_TIMEOUT", "30"))

# Caddy holds connections open; keep them alive slightly longer than its default
# so the proxy, not the app, decides when to close.
keepalive = 5

# --- process hygiene ---------------------------------------------------------
# Worker recycling is DISABLED (0) because there is only ONE worker. Recycling the sole worker means
# a window with nothing serving, and with slow streaming answers that window can
# swallow a user's in-flight request. With multiple workers, recycling is free
# because the others cover; with one it is a self-inflicted outage.
#
# The leak protection this gives up is instead covered by the container memory
# limit plus restart: always — a genuinely leaking worker gets OOM-killed and
# restarted, which is the same outcome, arrived at only when actually needed.
max_requests = int(os.getenv("GUNICORN_MAX_REQUESTS", "0"))
max_requests_jitter = 0

# Gunicorn heartbeats through a temp file. On containers whose /tmp is a slow or
# full overlay this causes spurious worker kills; /dev/shm is a tmpfs and is the
# documented fix.
worker_tmp_dir = "/dev/shm"

# preload_app is deliberately OFF. Preloading forks workers after the app (and
# its database connections) are created, which shares psycopg2 connections
# across processes and corrupts them. The memory saving is not worth it.
preload_app = False

# --- logging -----------------------------------------------------------------
# Both streams go to stdout/stderr so `docker compose logs` is the single place
# to look, and Docker's log rotation (Phase 5) governs retention.
accesslog = "-"
errorlog = "-"
loglevel = os.getenv("GUNICORN_LOG_LEVEL", "info")

# Access log includes response time (%(L)s, seconds) because answer latency is
# the operational metric that matters most here.
access_log_format = '%(h)s "%(r)s" %(s)s %(b)s %(L)ss "%(a)s"'

# Trust the X-Forwarded-* headers from Caddy only. Django additionally verifies
# the protocol via SECURE_PROXY_SSL_HEADER.
forwarded_allow_ips = os.getenv("GUNICORN_FORWARDED_ALLOW_IPS", "*")


# --- background work ---------------------------------------------------------
# The pre-computation refresher runs inside the worker rather than as a separate
# container because it must share the process-local LLM semaphore: it only
# generates when concurrency.queue_position() == 1, i.e. when no person is
# waiting, and that fact lives in this process. A separate container would
# either compete blindly for the model or need Redis-coordinated admission,
# which is the same change GUNICORN_WORKERS > 1 would need (see above).
def post_worker_init(worker):
    try:
        from orchestrator import precompute_refresher
        precompute_refresher.start()
    except Exception:  # never let background work stop the worker booting
        worker.log.exception("precompute refresher failed to start")
