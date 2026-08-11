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
| Existing session | **HTTP 503** — signed out, and told the service is down rather than that they were denied |
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

**First attempt** was to pass `_UnavailableSql` instead of `None`, routing the
outage through that existing, tested wording:

```
Database lookup FAILED (error: the records database was unreachable ...).
This means the lookup could not be performed. It does NOT mean the records
are absent. Do NOT state or imply that no such records exist...
```

Three regression tests pin it, covering synthesis, verification and the audit
metadata — verification matters because it was handed the same misleading
"none" and would otherwise rubber-stamp the false negative as consistent.

**That was not enough on its own — the model ignored it. See the next
section for what actually fixed it.**

---

## The false-absence defect — now fixed in code, not in a prompt

The three prompt attempts recorded above did not work, and a fourth was not
made. The decision was removed from the model instead.

**Two states are now distinguished before synthesis runs at all:**

| state | meaning | handling |
|---|---|---|
| query ran, zero rows | a fact about the college | unchanged — the model answers |
| query could not run | a fact about our infrastructure | the model does not decide |

**Case 1 — nothing else to answer from.** No LLM call happens. `_generate_stream`
returns `UNAVAILABLE_MESSAGE` directly from code. A test asserts the synthesis
function is never invoked.

**Case 2 — retrieval worked.** The note is emitted as literal text *before*
synthesis starts, and the model is never shown it and never asked to produce
it. It is also handed `sql_result=None`, so there is no failed lookup in its
prompt to write about.

**Case 2 needed one more thing.** Withholding the SQL section was not enough:
given no database data at all, the model still inferred absence from the
question and wrote the same sentence anyway, directly beneath a note
contradicting it. So `_strip_false_absence` removes such sentences after
generation — deterministic code, scoped to this path only, and conservative: a
sentence is dropped only if it matches an absence pattern **and contains no
digit**, so a real finding like *"63 Lecturers do not have a recorded score"*
survives.

### The live result

Signed in, Postgres stopped underneath the session, same question as before:

```
I couldn't retrieve that information right now due to a temporary system issue.
Please try again shortly.

However, for those departments that have data, the overall faculty development
index averages 67.2 out of 100, with varying scores in digital capability and
teaching quality. The most common competency level is "Advanced," and the most
frequent assessed development need is "Moderate Development Need."
```

```
STARTS WITH the note         : True
false-absence phrases present: NONE
route                        : RAG
```

The server log shows the filter doing its job:

```
removed 1 absence claim(s) from a degraded answer:
  ['The college records do not cover the total number of faculty holding the
    Lecturer rank across all departments.']
```

**19 tests** cover this, and they were verified to fail when the prepend is
removed — 4 of them break, so they are load-bearing rather than decorative.

### What this costs, stated plainly

- **Degraded answers are buffered, not streamed.** Sentence removal needs whole
  sentences and sentences span streamed chunks. Paid only during an outage, and
  only after the note has already appeared, so nobody watches a blank screen.
- **A removed sentence can leave a seam.** The live answer opens "However, for
  those departments that have data" — a "However" whose preceding clause is
  gone. Slightly odd, and much better than a false statement.
- **The filter is a blunt instrument.** It deletes model prose on a pattern
  match. It is confined to the one path where such a sentence is false by
  construction, and the digit guard keeps data-bearing sentences. It would be
  wrong to widen it.

## The three smaller residuals — all fixed

- **Audit during an outage.** The audit table is in the database, so the write
  fails exactly when the system is still answering. There is no second durable
  store, so the gap is now made VISIBLE instead of silent: the full record —
  user, IP, route, question, answer prefix, latency — goes to the application
  log at ERROR, which survives the database being down. Verified live:
  `AUDIT WRITE FAILED (could not translate host name "postgres" ...)`.
- **Route label.** An unavailable SQL result no longer counts as "SQL
  happened", so a degraded answer is recorded as `RAG`. Verified live:
  `route=RAG` where it previously said BOTH.
- **403 to 503 on a Redis outage.** Django's cache session backend swallows
  every exception in `load()` and treats an unreachable store as "not signed
  in", which told users their account was the problem. `config/session_store.py`
  lets connection errors propagate; `ResilientSessionMiddleware` stops the
  response-phase session save from replacing that 503 with a 500. Verified
  live: **503** with a plain sentence.

## What is still wrong

- **The 3B verifier still times out on long degraded answers**, so they carry
  "could not be fact-checked". Unchanged, and unrelated to this work.
- **Redis remains a single point of failure for sessions.** Accepted trade,
  measured above.

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

**Tests: 146 backend, all passing.** `ruff` clean.
