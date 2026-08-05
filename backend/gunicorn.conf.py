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

  threads = 4 (override with GUNICORN_THREADS)
      1 x 4 = 4 requests can be in flight at once. That is deliberately larger
      than LLM_MAX_CONCURRENCY (1): the extra threads are what allow a waiting
      request to be HELD and then told "busy" politely, rather than being
      refused at the socket with a connection error. Threads are cheap because
      they are parked on I/O, not computing.

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
threads = int(os.getenv("GUNICORN_THREADS", "4"))
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
