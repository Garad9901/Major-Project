# Phase 0 — survey and decisions: MS SQL migration and CPU latency

Copyright (c) 2026 Yash Garad. All rights reserved.

Status: **no code written.** This document is the Phase 0 deliverable.
Measured on the running stack, 2026-09-02, HEAD `3f6405c`.

---

## 1. Corrections to the brief

The brief is accurate on the numbers I could check, with three exceptions.

**327 tests, all passing — confirmed.** `Ran 327 tests in 90.383s / OK
(skipped=4)`. An earlier figure of 301 I quoted in conversation was stale by
several commits; the brief was right and I was wrong.

**No MS SQL connection exists anywhere today.** A search for
`pyodbc|mssql|SQL Server|tsql` across `backend/` and `sync_worker/` returns
nothing, and `DATABASES` holds a single `django.db.backends.postgresql`. The
migration *adds* a second database; it does not convert an existing one.

**The 4.3 file list is NOT complete.** It names 12 files, all of which exist.
One further file has real, code-level Postgres coupling:

| File | Coupling | Severity |
|---|---|---|
| `backend/sql_agent/service.py:5,44` | imports `psycopg2`; catches `psycopg2.OperationalError` to degrade gracefully when the records database is unreachable | **High** |

That catch is one of the outage-degradation paths section 5 says must not be
removed. `pyodbc` raises `pyodbc.OperationalError` / `pyodbc.Error`, which the
existing `except` will not catch — so during a college-DB outage the graceful
"having trouble reaching the records" path stops working and the user gets an
unhandled error instead. It fails in the least visible direction: only during
someone else's outage.

Six other files mention Postgres in comments or strings only and need no change
(`accounts/views.py`, `config/secret_guards.py`, `health/status_view.py`,
`institution/writer.py`, `web_agent/fetcher.py`, `common/env.py`). Under the
two-database split in 4.2 those references stay *correct*, because our own store
remains Postgres.

---

## 2. The LIMIT to TOP problem is much smaller than the brief expects

The brief calls `_cap_limit` "the single most error-prone change in the
migration". Measured, it is close to free.

The row cap is applied to the sqlglot **AST** and only then rendered:

```python
return _cap_limit(stmt, max_limit).sql(dialect=DIALECT)
```

sqlglot 30.17.0 renders the same capped AST correctly per dialect:

```
tsql  -> SELECT TOP 50 department, COUNT(*) FROM faculty_development GROUP BY department
pg    -> SELECT department, COUNT(*) FROM faculty_development GROUP BY department LIMIT 50
```

The row cap therefore survives the dialect switch as a one-constant change.
That is a material saving against the plan as written, and it is a direct
consequence of the original author enforcing the cap on the parse tree rather
than on text.

---

## 3. The real guard risk is OPENROWSET, and it is present today

While verifying the dialect switch I ran the T-SQL injection cases the brief
defers to Phase 2 against the **live** guard. Result:

| Case | Verdict |
|---|---|
| `SELECT department FROM faculty_development` | ALLOWED (correct) |
| `SELECT 1 FROM faculty_development; DROP TABLE departments` | REJECTED — stacked statements |
| `EXEC xp_cmdshell 'dir'` | REJECTED — not a SELECT |
| `WAITFOR DELAY '00:00:05'` | REJECTED — parse error |
| `SELECT name FROM sys.tables` | REJECTED — table not allowlisted |
| **`SELECT * FROM OPENROWSET('SQLNCLI','x','SELECT 1')`** | **ALLOWED** |
| **`SELECT * FROM OPENQUERY(linked,'SELECT 1')`** | **ALLOWED** |
| **`SELECT 1`** (no table at all) | **ALLOWED** |

### Mechanism

The allowlist enumerates table names and rejects any that are not permitted. A
query whose data source is a **function** rather than a named table yields no
usable table name:

```
SELECT 1                        tables_extracted=[]    -> ALLOWED
SELECT * FROM OPENROWSET(...)   tables_extracted=['']  -> ALLOWED
SELECT * FROM OPENQUERY(...)    tables_extracted=['']  -> ALLOWED
```

**The allowlist fails open on the empty set.** "No forbidden table was named" is
being treated as "every table named was permitted".

### Why it is harmless today and dangerous after Phase 2

Under `DIALECT = "postgres"` there is no `OPENROWSET`, so such a query dies at
execution. The moment the dialect becomes `tsql` against a real SQL Server,
`OPENROWSET` and `OPENQUERY` are live: they read remote data sources and files
from the perspective of the database server. That is a read the read-only
principal was never intended to grant, and `db_datareader` plus
`DENY INSERT/UPDATE/DELETE` does not prevent it, because it is a read.

### Recommendation

Fix this **before** Phase 2, as a Postgres-era hardening commit, not inside the
dialect switch. Two small changes:

1. Require at least one named data source, and require **every** data source to
   be a named, allowlisted table — reject a query that reaches zero named tables.
2. Reject table-valued functions in `FROM` outright: `OPENROWSET`, `OPENQUERY`,
   `OPENDATASOURCE`, `OPENXML`.

Landing it first means it ships with 327 green tests behind it and is verifiable
under the dialect we already understand, rather than entangled with the
migration.

---

## 4. Latency: recommendation on Section 3

**Agreed: A (deterministic-first), and A alone probably meets the requirement.**

The arithmetic in the brief is right and matches this project's own measurements
in `docs/SCALING.md` and `docs/LATENCY.md`: one answer is tens of seconds of CPU
inference, `LLM_MAX_CONCURRENCY=1` is correct rather than a tuning knob, so
capacity is queueing and `users ≈ queue_timeout / mean_answer_time`. No tuning
closes that gap.

Two additions to the brief's framing:

**A is not only faster, it is safer.** A templated answer over a parameterised
query cannot hallucinate, so it removes the failure this system fears most — a
wrong fee or deadline reaching a student — for exactly the questions most likely
to be asked. The first question asked in this session is the case in point:
"How many faculty are in the Computer Science department?" returned 1,916, which
is correct, in **215 seconds**, and then carried an unnecessary "could not be
confirmed" warning. That is a single indexed count.

**C is worth taking too, but for the tail rather than the median.** Once A serves
the common families, the LLM path holds only genuinely open questions — which is
where 3B's quality cost is most visible. Keep 7B for that remainder and revisit
only if the queue is still the constraint after A ships.

**B (GPU) should be priced anyway**, not adopted now. It is the only thing that
helps the open-ended tail, and knowing the number makes "CPU only" an informed
decision rather than an assumed one.

**D is the honest status quo** and should remain the behaviour underneath A: the
busy message stays for the LLM path.

---

## 5. Recommendations on Section 5 removals

| Candidate | Recommendation |
|---|---|
| `web_agent` (964 LOC + 381 test LOC) | **Delete, if the college confirms it does not need public-web answers.** It is the only inbound path for third-party content on an internet-facing system: SSRF surface and a prompt-injection channel at once. Needs confirmation — question 6. |
| `experiments/` (635 LOC) | **Exclude from the image, keep in the repo.** Agreed, low risk. |
| Demo commands + `seed_demo_data` | **Keep, gate hard.** Already defaults off; make it refuse to run when `DJANGO_ENV=production`. |
| `faculty_development` (13k rows, referenced by 13 files) | **Do not remove yet.** It is the only dataset the 327 tests and every measurement in `docs/` are calibrated against. Removing it before the real schema exists destroys the baseline needed to prove the migration did not regress. Remove in Phase 5, after Phase 2 proves the real schema works. |
| LLM verification pass | **Gate, default off — agreed.** Measure first: it costs a full model round-trip per answer, and it flagged a *correct* answer as unconfirmed on the first question asked this session. |

---

## 6. Proposed order — differs from the brief in one place

1. **Phase 0.5 — guard hardening** (new): fix the OPENROWSET / empty-allowlist
   failure under Postgres, with tests, while the suite is green.
2. Phase 1 — WSL2 + Docker on the Windows host; benchmark Ollama WSL2 vs native.
3. Phase 2 — MS SQL read path. Now a smaller change than budgeted: dialect
   constant, `sql_agent/service.py` exception handling, schema introspection,
   `db.py` driver, read-only principal.
4. Phase 3 — deterministic fast path. **The highest-value work.**
5. Phase 4 — Change Tracking sync.
6. Phase 5 — removals.
7. Phase 6 — security and load.
8. Phase 7 — handover.

---

## 7. What I have not verified

- Ollama throughput under WSL2 versus native Windows — no access to the target
  machine.
- Whether SQL Server Change Tracking can be enabled — a DBA decision.
- Whether the real college schema resembles the current `academics` models. It
  almost certainly does not, and Phase 3's question families cannot be designed
  until it is known.
- The 20-concurrent-user target under the deterministic path — not measurable
  until Phase 3 exists.
