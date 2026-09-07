# Product plan — generalising to any customer database

Copyright (c) 2026 Yash Garad. All rights reserved.

Phase 0 deliverable. Written after reading the reference implementation and
measuring the claims that the plan depends on, rather than accepting them.

---

## Decisions taken

| | |
|---|---|
| Repository | **Generalise in place.** One repo, one suite; the college becomes customer zero. |
| Engines | Postgres, SQL Server, MySQL/MariaDB, Oracle — **sequencing proposed below** |
| Hardware | CPU baseline, **GPU as a paid upgrade tier** |
| Operators | Customer IT |
| Scale | **100+ concurrent users** |

Two of these change the plan materially and are treated below rather than
absorbed silently.

---

## 1. The concurrency defect is real, and worse than the brief states

Measured on the running system. Four descriptive questions from distinct
accounts, then fast-path questions fired during saturation:

| | latency | route |
|---|---|---|
| fast path, idle | 177 / 189 / 367 ms | FAST |
| **fast path, 4 model requests in flight** | **17,173 ms** | FAST |
| the 4 model requests | 65,940 ms (1 served); 25,216 / 25,342 / 25,388 ms (**3 refused**) | RAG / busy |

A **47–97× degradation** on a question that never touches the model.

**The mechanism is not "the fast path waits for generation".** `8s + 17.2s ≈
25.2s`: the fast-path request was released at exactly the moment three model
requests hit `llm queue timeout after 25s` and gave back their threads. Log
confirms three timeouts and `llm queue: 3 waiting`.

So **fast-path starvation is bounded by `LLM_QUEUE_TIMEOUT`, not by model
speed** — `gunicorn` runs `gthread` with 4 threads, and
`_slots.acquire(timeout=25)` blocks while holding one.

### This inverts a recommendation already in this repository

`docs/SCALING.md:83` records a measured 50-user result and concludes:

> "the 25s queue timeout was mistuned and was refusing leaders that would have
> succeeded. `LLM_QUEUE_TIMEOUT=120`."

Applying that documented advice today would take fast-path starvation from
**17s to up to 120s**. Two recommendations in this codebase are in direct
conflict, and neither is wrong in isolation — each was measured alone.

**Consequence for ordering: Phase 1 must land before the queue timeout is ever
raised.** Recorded here because the next person to read SCALING.md will
otherwise apply a change that looks like a pure improvement.

---

## 2. 100 concurrent users breaks a second ceiling the brief does not mention

§6.5's fix — a queue between the web tier and inference — removes model requests
from the thread pool. It does **not** make 4 threads enough for 100 users.

Arithmetic from measured numbers, fast path only, no model involved:

```
fast path end to end        ~200 ms   (measured 177-368 ms)
threads                          4
throughput ceiling         4 / 0.2 = 20 requests/second
100 simultaneous arrivals  100 / 20 = 5.0 s to drain
                           p50 ~2.5 s, p95 ~4.75 s
```

Against a target of **p95 under 1 second**. The fast path is fast; the server
cannot hand out enough threads to use it.

To drain 100 requests inside 1s at 200 ms each needs **~20–24 threads**. That is
sound in principle — the fast path is I/O-bound (one indexed aggregate), not
CPU-bound, so the GIL is not the limit. But raising threads alone moves the
bottleneck rather than removing it:

| ceiling | value today | at 20+ threads |
|---|---|---|
| `RAG_AGENT_RO_POOL_MAX` | 8 | exhausted; the pool raises `DatabaseUnavailable` by design |
| `rag_agent_ro CONNECTION LIMIT` | 10 | refuses connections; shared with the sync worker |
| `DB_CONN_MAX_AGE` | 60 | 20 threads × persistent connections vs a limit of 10 |

The last row is the one that has already caused an outage on this project —
`docs/SCALING.md` records `CONN_MAX_AGE=60` exhausting Postgres under load. So
the thread count, the pool size and the role's connection limit must be raised
**together, as one change, with the reasoning recorded**, or the fix reproduces
a known incident.

**Phase 1 therefore has two parts, not one:** the inference queue (§6.5) *and*
the web-tier/pool/role sizing. Neither alone reaches the target.

---

## 3. Engine sequencing — a cost to accept before it is spent

All four engines were selected. Postgres and SQL Server already work end to end.
The other two are not configuration flags:

| engine | introspection | change feed | real cost |
|---|---|---|---|
| Postgres | done | watermark / logical replication | **shipped** |
| SQL Server | done | Change Tracking, proven locally | **shipped** |
| MySQL / MariaDB | moderate — `INFORMATION_SCHEMA` differs, no schemas | **binlog** — a different model from both above | one phase |
| Oracle | heavy — `ALL_TAB_COLUMNS`, identifier casing, `NUMBER` type mapping | **LogMiner / GoldenGate** | one phase, plus driver and licensing friction |

**Recommendation: ship Postgres + SQL Server, and build Phase 2's adapter
interface so MySQL and Oracle are additive rather than invasive.** Add them
against a named buyer, not speculatively. The reason is not effort but evidence:
every engine added before a real customer database is an engine whose
introspection is verified only against a schema we invented.

If a named buyer already requires MySQL or Oracle, that changes the answer and
the sequencing should follow the buyer. **Flagged, not decided.**

---

## 4. Tier boundaries — confirmed against the code

```
Tier 0  answer cache ............  126-472 ms measured   orchestrator/cache.py
Tier 1  deterministic fast path .  177-468 ms measured   fast_path/
Tier 2  SQL agent ...............  seconds-minutes       sql_agent/
Tier 3  retrieval + synthesis ...  65-87 s measured      rag_agent/ + synthesis_agent/
```

Tier 1 currently answers **72.8%** of real logged traffic (645/886 requests,
measured by replay). Target is 90–95%. The gap is almost entirely prose —
"Describe…", "Summarise…", "Compare…" — which is exactly what §6.4's
pre-computation converts into Tier 0 lookups. **Pre-computation, not more
intent families, is the route from 72.8% to 90%.**

---

## 5. Reuse map

**Reuse unchanged.** `sql_agent/guard.py` (sqlglot parsing, whole-identifier
validation, `OPENROWSET`/`OPENQUERY`/`xp_cmdshell` denial, tested under both
dialects); `orchestrator/cache.py`; `common/env.py`; `common/devonly.py`;
`common/schema_map.py`; `audit/`; the outage degradation paths;
`config/secret_guards.py`; the read-only principal model.

**Generalise, do not rewrite.** `fast_path/` is the right shape with
hand-written intents — Phase 3 generates families from introspection instead.
`fast_path/entities.py` already reads vocabulary from the database rather than
from code, which is §6.1's requirement already satisfied.
`common/schema_map.py` is already the logical→physical seam the adapter needs.

**Replace.** The blocking `llm_slot`.

**Add.** Adapter interface, install-time classification, coverage report,
confirmation screen, pre-computation.

---

## 6. Corrections to the brief

* **§4's "fast path p95 468 ms"** holds only on an idle system. Under model load
  it is **17s**. The figure needs its condition attached wherever it is quoted.
* **§6.5's mechanism** is accurate but the consequence is bounded by the queue
  timeout rather than by generation, which is what makes §1 above urgent
  relative to the SCALING.md change.
* **§7's "warm on boot"** is already implemented — `ollama-pull` preloads and
  health reports `warming` until models are resident. The real gap is different:
  `restart: "no"` means it does **not** re-run after a daemon or host restart, so
  a rebooted server returns looking healthy and serving timeouts. Observed twice
  during this work.

---

## 7. Phase order

Unchanged from the brief except that **Phase 1 gains the sizing work** from §2.

0. **Survey** — this document. ✅
1. **Concurrency** — inference queue; thread/pool/role sizing as one change.
   Proof: saturate the model path, show fast-path p95 unchanged, and separately
   show 100 concurrent fast-path users at p95 < 1s with distinct accounts.
2. **Adapter layer** — one interface; Postgres + SQL Server; introspection
   verified **as the read-only principal**, since catalog views are
   privilege-filtered and return fewer rows rather than erroring.
3. **Install-time adaptation** — classification, vocabulary, family generation,
   coverage report, confirmation screen.
4. **Fast path + pre-computation** — 90%+ measured against a realistic set.
5. **Model path** — SQL-specialised model, self-correction, verification.
   No schema linking, no self-consistency.
6. **Sync worker** — change tracking, incremental re-embed, resumption proven by
   killing it mid-run.
7. **Security and load** — read-only proven by observed state; guard suite
   against the real executor; per-user quotas; audit coverage including the fast
   path; load test with distinct accounts.
8. **Packaging** — installer, health, backup with tested restore, runbook.

---

## 8. Not verified

* The 100-user arithmetic in §2 is **derived from a measured single-request
  latency, not measured at 100 users.** No 100-user test has been run on this
  hardware. It establishes that 4 threads cannot meet the target; it does not
  establish that 24 threads can.
* MySQL and Oracle introspection has not been attempted at all.
* Pre-computation is projected to close the 72.8% → 90% gap based on the shape
  of the remaining misses. That is an inspection of question text, not a
  measurement.
