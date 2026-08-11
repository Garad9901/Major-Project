# Resilience — before and after Redis-backed sessions

Copyright (c) 2026 Yash Garad. All rights reserved.

**Date:** 11 August 2026
**Change:** sessions, the login lockout and the rate-limit counters moved from
Postgres to Redis; identity cached as an outage fallback; two defects found and
fixed during the re-test.
**Method:** each service stopped in turn against the running stack, a question
asked, the service restarted, the same question re-asked. For the database
phase the user is signed in **before** the outage, which is the case the
previous run could not test at all.

---

## The gap this closes

The production-readiness pass found that a Postgres outage took authentication
down with it. Sessions were database rows, so with Postgres stopped:

- `POST /api/auth/login/` returned **HTTP 500**
- every request from an already-signed-in user failed on session lookup

The orchestrator has a deliberate degradation path — database down, answer from
the vector store, tell the user the records lookup is unavailable. It works, it
is tested, and it was **unreachable**, because nobody could hold a session long
enough to reach it.

---

## Before / after

| With Postgres stopped | Before | After |
|---|---|---|
| Existing session (`GET /api/auth/me/`) | **HTTP 500** | **HTTP 200** |
| Signed-in user asks a question | **impossible — could not authenticate** | **HTTP 200, answered from the vector store** |
| "records unavailable" note present | n/a | **yes** |
| New sign-in | **HTTP 500** (198 KB debug traceback) | **HTTP 503** + one plain sentence |
| Health reporting | one "Database" row | `database: down`, **`sessions: up`** |
| Recovery | pass | pass |

```
[4] GET /api/auth/me/ -> HTTP 200   (the session survived a database outage)
[5] BOTH-route question while the database is down:
      http=200 route=BOTH
      contains a 'records unavailable' note: True
[6] NEW sign-in during the outage:
      login: HTTP 503
      "Sign-in is temporarily unavailable while the college records system is
       being restored... Anyone already signed in can continue."
[7] after recovery, same session: http=200 "There are 2,073 faculty..."
```

### A new sign-in during a database outage still fails. That is correct.

It is called out here because it looks like a gap and is not one. Verifying a
password needs the password hash, and the hash lives in Postgres. Checking a
credential against a store you cannot read is not something to engineer around,
and no session change could alter it.

What changed is the *shape* of the failure: an unhandled `OperationalError`
became a 500 — rendered in development as a 198 KB debug traceback — and is now
a 503 carrying a sentence that also tells the user existing sessions are fine.

---

## Redis sessions alone were NOT enough

Worth recording, because the change would otherwise have shipped as a fix that
did not fix anything. After switching `SESSION_ENGINE`, the session cookie
resolved without Postgres — and an authenticated request **still returned 500**.

Django's `AuthenticationMiddleware` does this on every request:

```
request.user = backend.get_user(session["_auth_user_id"])   # SELECT FROM auth_user
```

and `CanUseAssistant` then reads `user_profile`. Two database round trips per
request, neither of them the session.

**`accounts/auth_backends.CachedModelBackend` closes it.** The database is asked
**first, every time**; a cached identity is used **only** when the database
raises. That ordering is the security argument:

- normal operation has **zero staleness** — every request sees the live row
- a stale identity can only be served while Postgres is unreachable
- revocation is unaffected: `disable_user` and `reset_password` delete the
  session from Redis, and a deleted session never authenticates

Bounded by `IDENTITY_CACHE_SECONDS` (default 1800). See `accounts/identity.py`
for the full reasoning, including why the password hash is part of the cached
record.

---

## What stopping REDIS does — the dependency this introduces

Measured rather than assumed, because trading one unknown for another is not a
fix.

| With Redis stopped | Result |
|---|---|
| Health | `database: up`, **`sessions: down`** |
| Existing session | HTTP 403 — signed out |
| New sign-in | **HTTP 503** + plain sentence (was 500 until fixed, see below) |
| Recovery | sign-in works immediately; answers normal |

Everyone is signed out while Redis is down. That is inherent and accepted: the
exposure is smaller than the one it replaces, because Redis does one simple
thing and is not the component that falls over under a heavy report. It runs
with `restart: always` and AOF persistence (`appendfsync everysec`) so a restart
does not sign everyone out, and `maxmemory-policy noeviction` so memory pressure
fails loudly instead of silently deleting people's sessions.

---

## Every service

| Stopped | Behaviour | Recovery |
|---|---|---|
| **postgres** | signed-in users keep working, answers degrade to the vector store with a note; new sign-ins get a clean 503 | PASS |
| **redis** | everyone signed out; clean 503 on sign-in | PASS |
| **qdrant** | records questions unaffected (`route=SQL`, 2,073 correct) | PASS |
| **sync_worker** | no user-visible effect at all | PASS |
| **ollama** | *"The AI service is temporarily unavailable"* — no traceback, no invented answer | PASS¹ |

¹ The automated run recorded ollama as FAIL. That was the **test's** fault, not
the system's: it waited for the container healthcheck, which passes as soon as
`ollama list` responds — minutes before the 7B model is resident in RAM. Re-run
by hand with an adequate wait, the same question streamed a correct answer.

---

## Two defects found by this re-test, both fixed

### 1. A Redis outage made sign-in return 500

The same defect that had just been fixed for Postgres, reappearing one component
to the left: `redis.exceptions.ConnectionError` propagated as a 500.

Fixed with `config.middleware.SessionStoreUnavailableMiddleware`, placed
**above** `SessionMiddleware` — the session middleware is itself one of the
things that raises, both loading the session on the way in and re-saving it on
the way out under `SESSION_SAVE_EVERY_REQUEST`. A `try/except` in the view would
have covered neither, nor the DRF throttles, which touch Redis before the view
runs. Verified: **500 → 503**.

### 2. A database outage was described to the model as "no data"

The serious one. With Postgres down, `_gather_sources` degraded to RAG and left
`sql_result` as `None`, which renders in the synthesis prompt as
`"Database rows: none."`. The model read that as absence and told the user:

> *"The college records do not cover the total number of faculty holding the
> Lecturer rank"*

against a table holding **3,053** of them.

That is the confident false negative the original production audit called the
worst failure shape this system has — arriving through a path that audit's fix
did not cover. Its careful wording in `synthesis_agent/untrusted.py` keys off
`sql_result.error`, and an outage never set one.

**Fixed** by passing `_UnavailableSql` instead of `None`, which routes the
outage through that existing, tested wording:

```
Database lookup FAILED (error: the records database was unreachable ...).
This means the lookup could not be performed. It does NOT mean the records
are absent. Do NOT state or imply that no such records exist...
```

Three regression tests pin it, covering synthesis, verification and the audit
metadata — verification matters because it was handed the same misleading
"none" and would otherwise rubber-stamp the false negative as consistent.

**AND IT IS STILL NOT ENOUGH — see below.**

---

## What is still wrong

### The model ignores the instruction anyway

With the prompt now explicitly saying the lookup FAILED and that this does not
mean the records are absent, `qwen2.5:7b` still opened its degraded answer with:

> *"The college records don't cover the total number of faculty holding the
> Lecturer rank across all departments."*

Three attempts have not moved it:

1. the existing `untrusted.py` wording (`does NOT mean the records are absent`)
2. `_UnavailableSql`, which is what makes that wording fire at all
3. an explicit template added to the synthesis system prompt telling it to write
   *"I couldn't retrieve that right now"* and never *"the records don't cover"*

The likely reason is that the style prompt hands the model an exact template for
missing data — `"The college records don't cover X."` — and templates get
copied. Giving it a competing template did not outrank the one it already knew.

**The user-facing note IS appended**, so the answer is self-contradictory rather
than purely false: it says the records do not cover the figure, and then says
the records lookup was unavailable. That is better than the original defect and
worse than correct.

**The fix is probably not more prompt text.** The deterministic option is to put
the "records lookup unavailable" note at the START of the answer instead of the
end, so the caveat is read first. That means emitting it before synthesis
begins, which restructures the streaming assembly path — not something to change
without time to re-verify the whole streaming, caching and coalescing chain.
Left undone deliberately.

### Smaller residuals

- **Route labelling.** With `_UnavailableSql` in place the effective route on a
  degraded BOTH question is now reported as `BOTH` rather than `RAG`, because
  the sentinel is not `None`. The answer is unaffected; the audit log's route
  field is now less precise for that case.
- **Nothing is audited during a database outage.** Questions are answered, but
  `AuditLog.objects.create` fails and is swallowed by design. For a system whose
  audit log is the accountability record, an outage is a blind spot.
- **An existing session gets 403, not 503, when Redis is down.** Technically it
  is "not authenticated", but it reads to the user as "your login is invalid"
  rather than "the service is degraded". They then hit the login page, which
  does say 503.

---

## Configuration added

```
REDIS_URL=redis://redis:6379/0     # add a password: redis://:<pw>@redis:6379/0
REDIS_MAXMEMORY=256mb
REDIS_CONNECT_TIMEOUT=2            # seconds; bounds a hung request
REDIS_SOCKET_TIMEOUT=2
REDIS_KEY_PREFIX=college
POSTGRES_CONNECT_TIMEOUT=3         # was unset — libpq waits forever by default
IDENTITY_CACHE_SECONDS=1800        # how long a cached identity survives an outage
```

`POSTGRES_CONNECT_TIMEOUT` was added after `GET /api/auth/me/` **hung** rather
than failing during the first re-test. A hang is worse than an error: production
runs one gunicorn worker with four threads, so four hung requests take the whole
site down, including the cached answers and the status page that would explain
why.

**Tests: 124 backend (was 121), all passing.** `ruff` clean.
