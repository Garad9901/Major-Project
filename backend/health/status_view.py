# Copyright (c) 2026 Yash Garad. All rights reserved.

"""A single status page an operator can open in a browser.

WHY A PAGE AND NOT JUST JSON
/api/health/ already returns JSON and is what the container healthcheck and any
future monitoring uses. It is not what a person uses at 9am when someone says
"the assistant isn't working". This renders the same information as a page that
loads in one click, refreshes itself, and says in words which component is at
fault and what to do about it.

WHY IT IS PUBLIC (AND WHAT THAT COSTS)
No login required. The reasoning: the people most likely to need it are locked
out precisely when authentication is the thing that is broken, and a status page
behind the auth system cannot tell you the auth system is down.

The cost is that anyone who can reach the URL learns which components exist and
whether they are healthy. That is accepted deliberately, and it is why this page
exposes NO counts, NO data, NO versions and NO configuration — only up/down per
component. An attacker learns that a college runs a database, which they could
have guessed.

If the institute would rather it were private, gate it behind IsAuthenticated —
but then also keep an unauthenticated way to check, or the first outage that
touches the database makes the status page useless too.
"""

import logging
import os
import time

from django.db import connections
from django.http import HttpResponse
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny

from common import ollama
from rag_agent import vector_store
from institution import config as institution_config

logger = logging.getLogger("health")


def _timed(fn):
    """Run a check, returning (ok, milliseconds). Never raises."""
    started = time.perf_counter()
    try:
        ok = bool(fn())
    except Exception as exc:
        logger.warning("status: check failed: %s", exc)
        ok = False
    return ok, round((time.perf_counter() - started) * 1000)


def _database():
    with connections["default"].cursor() as cur:
        cur.execute("SELECT 1;")
        return cur.fetchone() is not None


def _redis():
    """Sessions, the login lockout and the rate-limit counters.

    ITS OWN ROW, not folded into "Database", because the failure it represents
    is completely different and the remedy is different. Postgres down means
    answers lose their records lookup but signed-in users keep working. Redis
    down means NOBODY is signed in — every session evaporates at once, and the
    symptom an operator sees is "everyone got logged out", which points nowhere
    near a database row on a status page.

    Writes and reads back rather than pinging, because a Redis that accepts
    connections but refuses writes — which is exactly what `maxmemory-policy
    noeviction` does when full — would pass a ping and still be unable to hold
    a single new session.
    """
    from django.core.cache import cache

    probe = "health-probe"
    cache.set(probe, "ok", 10)
    return cache.get(probe) == "ok"


def _readonly_role():
    """The read-only path specifically, which the app-owner check does not cover.

    Worth its own line: the assistant can look perfectly healthy while being
    unable to answer a single question, because these are different credentials
    against different grants.
    """
    from sql_agent import db
    with db.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1;")
            return cur.fetchone() is not None


# How far the index may lag the database before it is called stale. The worker
# polls every SYNC_WORKER_POLL_INTERVAL_SECONDS (30 by default), so a few
# minutes of tolerance keeps a normal cycle — or one slow re-embed — from
# flapping the dashboard, while still catching a worker that has actually died.
_STALENESS_TOLERANCE_SECONDS = int(os.getenv("SYNC_STALENESS_TOLERANCE", "600"))

# The table this check measures. Descriptive, embedded, and the one the RAG path
# actually retrieves from, so its freshness is what users experience.
_FRESHNESS_TABLE = "faculty_development_profiles"


def _index_is_fresh():
    """Is the search index still keeping up with the database?

    WHY THIS CHECK EXISTS, AND WHY PINGING THE WORKER WOULD NOT DO
    Every other row on this page is a liveness probe, and during the audit all
    of them stayed green while the sync worker was stopped outright — the page
    said "All systems operational" with nothing syncing at all. It also said
    that while the worker was in a crash loop on a corrupt state file. In both
    cases the first sign of trouble would have been a user quietly receiving
    last week's answer.

    This compares what the index holds against what the database holds, so it
    reports the thing that actually matters. It catches a stopped worker, a
    crash-looping worker, AND a worker that is running but wedged — which a
    container healthcheck or a liveness ping cannot distinguish from healthy.

    Deliberately fails OPEN. If either side cannot be read, this returns True
    rather than painting the page red: Qdrant and Postgres each have their own
    row above, and a second alarm for an outage already reported is noise. This
    row answers one question only — given that both are up, is the index current.
    """
    with connections["default"].cursor() as cur:
        cur.execute(f"SELECT max(updated_at) FROM {_FRESHNESS_TABLE};")  # noqa: S608 - constant
        row = cur.fetchone()
    db_newest = row[0] if row else None
    if db_newest is None:
        return True  # nothing to sync yet

    index_newest = vector_store.newest_indexed_updated_at(_FRESHNESS_TABLE)
    if index_newest is None:
        # Either Qdrant is unreachable (its own row covers that) or the table has
        # never been indexed. The latter is genuinely wrong, but only once there
        # is something to index — and there is, since db_newest is not None.
        return False

    lag = (db_newest - index_newest).total_seconds()
    if lag > _STALENESS_TOLERANCE_SECONDS:
        logger.warning(
            "search index is stale: %s newest row is %.0fs ahead of the newest "
            "indexed point (tolerance %ss) — is sync_worker running?",
            _FRESHNESS_TABLE, lag, _STALENESS_TOLERANCE_SECONDS,
        )
        return False
    return True


def _language_model():
    """Resident, not merely reachable.

    This was `ollama.ping`, which GETs /api/tags — the models on DISK. It
    answers 200 the moment the server is listening, so the dashboard showed a
    green "Language model" row for the ~15 minutes a fresh deployment spends
    loading, while every question timed out. Demonstrated by unloading all
    three models and reloading this page: still green.

    Returns False while warming, so the row goes red and REMEDY explains it.
    That is the honest signal: the system genuinely cannot answer a question
    yet.
    """
    ready, _detail = ollama.is_ready()
    return ready


CHECKS = [
    ("Database", _database, "Postgres — records, accounts and history"),
    ("Sessions & sign-in", _redis, "Redis — keeps people signed in and enforces the login lockout"),
    ("Read-only DB role", _readonly_role, "The restricted account the assistant queries with"),
    ("Language model", _language_model, "Ollama — answers questions"),
    ("Search index", vector_store.ping, "Qdrant — finds descriptive content"),
    ("Index freshness", _index_is_fresh,
     "Whether sync_worker is still copying database changes into the search index"),
]

# What to do about each, shown only when that component is down. An operator
# reading this page is often not the person who built it.
REMEDY = {
    "Database": (
        "docker compose ... restart postgres — then check disk space on the server. "
        "Signed-in users can still ask questions while this is down; their answers "
        "come from the search index and say so. New sign-ins will not work until "
        "it is back."
    ),
    "Sessions & sign-in": (
        "docker compose ... restart redis. Everyone is signed out until it returns, "
        "and signing back in works as soon as it does. If it restarts but stays red, "
        "check `docker compose logs --tail 50 redis` for OOM — the keyspace is capped "
        "and set to reject writes rather than silently evict people's sessions."
    ),
    "Read-only DB role": "Restart the backend; it recreates the role and its grants on startup.",
    "Language model": (
        "If this is a fresh start or a restart, it is LOADING and will clear on "
        "its own — allow up to 15 minutes on CPU-only hardware. This row is red "
        "rather than amber on purpose: until the model is resident the assistant "
        "genuinely cannot answer, and questions will time out. If it stays red "
        "well past that, check `docker compose ... logs ollama` and that the "
        "server has enough free RAM to hold the models."
    ),
    "Search index": "docker compose ... restart qdrant. Descriptive answers degrade; database answers keep working.",
    "Index freshness": (
        "sync_worker has stopped keeping up. Check `docker compose ps sync_worker` "
        "and `docker compose logs --tail 50 sync_worker`. Answers are still being "
        "given, but descriptive ones may be out of date."
    ),
}

_PAGE = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="15">
<title>{title}</title>
<style>
 :root{{color-scheme:light dark}}
 body{{font:15px/1.6 system-ui,-apple-system,Segoe UI,sans-serif;margin:0;padding:2rem 1rem;
       background:#fff;color:#111}}
 main{{max-width:46rem;margin:0 auto}}
 h1{{font-size:1.35rem;margin:0 0 .25rem}}
 .sub{{color:#666;font-size:.85rem;margin:0 0 1.5rem}}
 .banner{{padding:.9rem 1.1rem;border-radius:.6rem;font-weight:600;margin-bottom:1.5rem}}
 .ok{{background:#e7f6ec;color:#0b6b2f}}
 .bad{{background:#fdecec;color:#a11}}
 table{{width:100%;border-collapse:collapse}}
 td,th{{text-align:left;padding:.6rem .5rem;border-bottom:1px solid #e5e5e5;vertical-align:top}}
 th{{font-size:.75rem;text-transform:uppercase;letter-spacing:.04em;color:#666}}
 .pill{{display:inline-block;padding:.15rem .55rem;border-radius:1rem;font-size:.78rem;font-weight:600}}
 .pill.up{{background:#e7f6ec;color:#0b6b2f}} .pill.down{{background:#fdecec;color:#a11}}
 .desc{{color:#666;font-size:.82rem}}
 .fix{{color:#a11;font-size:.82rem;margin-top:.3rem}}
 .ms{{color:#888;font-size:.8rem;font-variant-numeric:tabular-nums}}
 footer{{margin-top:1.5rem;color:#888;font-size:.78rem}}
 @media (prefers-color-scheme:dark){{
   body{{background:#0f0f10;color:#eee}} td,th{{border-color:#2a2a2c}}
   .ok{{background:#0e2f1c;color:#7fdba4}} .bad{{background:#3a1414;color:#ffa3a3}}
   .pill.up{{background:#0e2f1c;color:#7fdba4}} .pill.down{{background:#3a1414;color:#ffa3a3}}
   .desc,.sub,.ms,footer{{color:#999}}
 }}
</style></head><body><main>
<h1>{institution} — system status</h1>
<p class="sub">{host} · checked {now} UTC · refreshes every 15s</p>
<div class="banner {banner_class}">{banner}</div>
<table>
<tr><th>Component</th><th>Status</th><th>Response</th></tr>
{rows}
</table>
<footer>Machine-readable version: <code>/api/health/</code> — returns HTTP 503 when anything is down.</footer>
</main></body></html>
"""

_ROW = """<tr>
 <td><strong>{name}</strong><div class="desc">{desc}</div>{fix}</td>
 <td><span class="pill {cls}">{state}</span></td>
 <td class="ms">{ms} ms</td>
</tr>"""


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def status_page(request):
    """Human-readable status dashboard at /api/health/status/."""
    results = [(name, desc, *_timed(fn)) for name, fn, desc in CHECKS]
    down = [name for name, _desc, ok, _ms in results if not ok]

    rows = "".join(
        _ROW.format(
            name=name, desc=desc,
            cls="up" if ok else "down",
            state="Operational" if ok else "DOWN",
            ms=ms,
            fix="" if ok else f'<div class="fix">Try: {REMEDY.get(name, "check the container logs")}</div>',
        )
        for name, desc, ok, ms in results
    )

    if down:
        banner = f"{len(down)} component{'s' if len(down) > 1 else ''} down: {', '.join(down)}"
    else:
        banner = "All systems operational"

    html = _PAGE.format(
        title="Status — All operational" if not down else f"Status — {len(down)} DOWN",
        # Reads the configured institution rather than a baked-in name. Falls
        # back to a neutral label rather than a placeholder institution: an
        # operator seeing "Academic Information Service" knows nothing is
        # configured, whereas a plausible wrong name tells them nothing.
        institution=(
            institution_config.get().get("institution", {}).get("name")
            or "Academic Information Service"
        ),
        host=request.get_host(),
        now=time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
        banner=banner,
        banner_class="ok" if not down else "bad",
        rows=rows,
    )
    # 503 when degraded so an uptime monitor pointed here reacts, not just a human.
    return HttpResponse(html, content_type="text/html; charset=utf-8",
                        status=200 if not down else 503)
