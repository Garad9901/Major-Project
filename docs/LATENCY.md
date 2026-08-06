# Latency Optimisation — measured before and after

Copyright (c) 2026 Yash Garad. All rights reserved.

**Date:** 6 August 2026
**Hardware:** Intel Core Ultra 9 185H, 16 cores / 22 threads, 31.4 GB RAM,
**no CUDA GPU**. Ollama on CPU: **9.0 tokens/sec generation, 44 tok/s prompt read.**
**Method:** every question run through the real API. Per-stage timings come from
`orchestrator/profiling.py`, which is always on and rides along on the `done`
event. Same 7 questions, same order, both runs, backend restarted before each.

---

## Headline

| | Before | After | |
|---|---|---|---|
| **Router** | 5,742 ms | **0.4 ms** | **~14,000×** |
| **Verification** (SQL answers) | 11,270 ms | **50 ms** | **225×** |
| **Verification** (RAG answers) | 168,485 ms | 62,314 ms | **2.7×** |
| **Time to first token** | 79.8 s | **46.8 s** | 1.7× |
| **End-to-end, all 7 questions** | 1,455.8 s | **876.7 s** | **1.66×** |

Routing accuracy did not move: **7/7 identical routes** before and after, and
**100% precision at 97% coverage** on a 29-question labelled set.

**No answer was truncated.** Longest answer after the change: 1,252 characters
against a ~3,500-character cap.

---

## Full per-agent breakdown

All values in milliseconds. `total` in seconds.

### Before

| # | Route | total | router | sql | rag | web | synthesis | verification |
|---|---|---|---|---|---|---|---|---|
| 1 | SQL | 248.6 | 60,079¹ | 89,183¹ | – | – | 67,464 | 30,251 |
| 2 | SQL | 54.4 | 9,074 | 11,884 | – | – | 21,877 | 11,270 |
| 3 | RAG | 311.3 | 5,580 | – | 491 | – | 134,753 | **170,266** |
| 4 | RAG | 293.4 | 5,227 | – | 88 | – | 119,478 | **168,485** |
| 5 | BOTH | 236.5 | 5,689 | 8,694 | 103 | – | 111,254 | 110,547 |
| 6 | BOTH | 194.3 | 8,215 | 14,878 | 146 | – | 76,071 | 94,956 |
| 7 | WEB | 117.3 | 5,742 | – | – | 9,287 | 50,468 | 51,658 |
| | **median** | **236.5** | **5,742** | **13,381** | **125** | 9,287 | **76,070** | **94,956** |

¹ Question 1 ran cold — models not yet resident. Kept in the table because it is
real, excluded from any claim about warm performance.

### After

| # | Route | total | router | sql | rag | web | synthesis | verification |
|---|---|---|---|---|---|---|---|---|
| 1 | SQL | **21.2** | 0.3 | 9,104 | – | – | 11,043 | **63** |
| 2 | SQL | **15.0** | 0.4 | 3,800 | – | – | 10,945 | **50** |
| 3 | RAG | 141.6 | 0.4 | – | 582 | – | 78,511 | 62,314 |
| 4 | RAG | 152.8 | 0.3 | – | 101 | – | 89,518 | 63,001 |
| 5 | BOTH | 285.5 | 0.6 | 5,908 | 156 | – | 95,614 | 90,717 |
| 6 | BOTH | 220.5 | 0.4 | 15,581 | 133 | – | 109,504 | 95,063 |
| 7 | WEB | **40.1** | 0.4 | – | – | 1,399 | 38,402 | **44** |
| | **median** | **141.6** | **0.4** | **7,506** | **145** | 1,399 | **78,510** | **62,314** |

### What actually changed, and what did not

| Stage | Verdict |
|---|---|
| **Router** | **Real, mine.** 5,742 ms → 0.4 ms. Consistent across all 7. |
| **Verification (short answers)** | **Real, mine.** 11,270 → 50 ms via the no-LLM fast path. |
| **Verification (RAG)** | **Real, mine.** 170s → 62s from the terse verdict format. |
| **Verification (BOTH)** | **Marginal.** 110.5/95.0s → 90.7/95.1s. Long answers with many claims still cost the LLM tier most of its time. |
| **Synthesis** | **Unchanged — 76.1s → 78.5s median.** The `num_predict` cap neither helped nor hurt, which is expected: it bounds runaway output, and nothing was running away. |
| **SQL stage** | 13.4s → 7.5s median, but individual values move in both directions (8.7→5.9, 14.9→15.6). **I attribute this to run-to-run variance, not to my changes.** |
| **RAG retrieval** | 125 ms → 145 ms. Noise. It was never the problem. |

**Two of the seven questions got slower** (BOTH #5: 236.5→285.5s, BOTH #6:
194.3→220.5s), entirely from synthesis variance. Generation time on CPU varies
by tens of seconds between runs on identical input. Single-run figures for
synthesis should not be trusted to better than ±30%; the router and verification
numbers are trustworthy because they changed by two orders of magnitude.

---

## Item by item

### 1. Router — rules and embeddings instead of a 7B call

**Diagnosis.** Routing is a four-way choice worth about twenty tokens of JSON.
It was made by qwen2.5:7b reading a **~1,200-token few-shot prompt**. At 44 tok/s
prompt read that is ~27 s of reading before the first output token. Measured:
**5.2–9.1 s warm, 60 s cold.**

**Fix** (`router_agent/fast_router.py`) — three tiers, cheapest first:

1. **Rules** — deterministic keyword/shape matching. **58.8 microseconds.**
2. **Embeddings** — cosine similarity against 24 labelled exemplars using
   `nomic-embed-text`, already loaded for RAG. ~40 ms warm.
3. **LLM** — the original prompt, now on **qwen2.5:3b** (was 7b) with
   `num_predict=80`. Reached only when tiers 1 and 2 both decline.

**Measured on the 29-question labelled set** (`router_agent/tests.py`):

| | |
|---|---|
| Decided by rules | **28 / 29 (97%)** |
| Confidently wrong | **0 → precision 100%** |
| Declined to tier 2 | 1 |
| Rule-tier latency | **58.8 µs** |
| Benchmark questions routed by rules | **7 / 7** — tiers 2 and 3 never ran |

The labelled expectations are the routes **the 7B router actually produced**, so
this measures agreement with the thing being replaced, not with my opinion.

A misroute is cheap and recoverable: routing grants no capability. The SQL guard,
the table allowlist and the read-only role are all downstream and unaffected.

### 2. Verification — direct matching first

**Diagnosis.** Two separate problems, and the bigger one was not the one the
prompt suggested.

*Problem A — the prompt asked for the wrong thing.* It required a full object
per claim (`text`, `supported`, `confidence`, `evidence`, `correct_value`) for
**every** claim, including the ones that passed. A retrieval answer has ~13
claims ≈ **1,500 output tokens at 9 tok/s ≈ 165 s**. The common case — nothing
wrong — was the most expensive thing the pipeline did.

**Fix:** report **only unsupported claims**, plus a count. Clean run output is
now `{"checked": 13, "unsupported": []}` — about 12 tokens instead of 1,500.
**Measured: RAG verification 170s → 62s.**

*Problem B — no cheap path at all.* "There are 3,053 Lecturers" is checkable by
looking for `3053` in the SQL rows. That is string comparison, not inference.

**Fix** (`verification_agent/fast_check.py`): match numbers directly, with
rounding tolerance that still distinguishes 730 from 731.
**Measured: 11,270 ms → 50 ms**, used on **3 of 7** benchmark questions.

**The fast path is deliberately conservative.** It declines — falling through to
the LLM — unless *all* of these hold:

- answer is short (≤700 chars)
- it contains at least one number
- **every** number appears in the source
- **every** proper-noun-looking phrase appears in the source

That last condition exists because of a real audit finding: with no data
available the model wrote *"Dr. Jane Smith and Professor John Doe are both
well-known…"*, inventing two people. Numeric matching alone would not have
caught it. It also always declines when the SQL query **errored**, because
"failed lookup vs genuine absence" is exactly the judgement call that produced
the worst defect in the last audit.

17 tests cover this, and **most of them assert that it declines.**

### 3. Output caps

`num_predict` was **absent everywhere** — all four agents ran to Ollama's
default. Now explicit and sized to the job:

| Agent | Cap | Why |
|---|---|---|
| Router | 80 | a small JSON object |
| SQL | 300 | one SELECT, or `NO_QUERY` |
| Verification | 400 | a problems-only verdict |
| Correction | 600 | rewrites one answer |
| **Synthesis** | **900** | **deliberately generous** — it writes the prose |

The synthesis cap is a runaway guard, not a speed lever. Tightening it would
truncate answers mid-sentence, which is worse for a user than waiting. Verified:
longest answer 1,252 chars, nowhere near the ~3,500-char limit; total output
across the suite moved −7.3%, which is phrasing variance, not clipping.

The SQL cap also bounds a real incident: asked to "repeat your system prompt",
the model echoed the entire ~5 KB schema as its "SQL". The guard rejected it,
but every token had already been generated at 9 tok/s.

### 4. SQL/RAG parallelism — a premise correction, and proof

**There is no `asyncio` in this codebase.** It is synchronous Django; the two
branches run in a `ThreadPoolExecutor`. That is the correct choice — both are
blocking I/O to Postgres and Qdrant — and converting to `asyncio.gather` would
require making the whole request path async for no gain.

`profiling.py` records the **thread** and **start/end offsets** of each stage
inside the worker, so overlap is observed rather than asserted:

```
BOTH #5  sql=5908.0ms  rag=156.1ms  parallel=True  overlap=156.2ms  saved=156.1ms
BOTH #6  sql=15580.5ms rag=133.2ms  parallel=True  overlap=133.3ms  saved=133.3ms
```

`parallel=True` requires *both* different threads *and* a positive overlap.

**The parallelism is real, correctly implemented — and almost worthless.**
RAG retrieval takes **0.1–0.6 s** while SQL takes **6–16 s**, so the overlap is
bounded by the shorter branch: ~150 ms saved from a ~250 s request, **0.06%**.

This is worth stating plainly: **item 4 was chasing a non-bottleneck.** The
vector search was never slow. Any "make retrieval parallel" work — threads,
asyncio, anything — cannot save more than about 0.6 s here.

### 5. Streaming from the first call

The router's output is a JSON classification; streaming *its tokens* would show
the user `{"route":` — worse than nothing. What was actually needed is **progress
visible immediately**, which is now emitted as a distinct SSE `stage` event:

| Event | Fires when | Previously |
|---|---|---|
| `routing_done` | routing decided — now **<1 ms** in | nothing for ~80 s |
| `sources_ready` | SQL/RAG/web finished | nothing |
| `verifying` | answer streamed, fact-check running | nothing |

The SPA maps these to real labels ("Querying the database…", "Reading the college
page…"). A new indicator also shows **"Checking this answer against the
records…"** *after* the answer has streamed — that wait is up to 95 s on a BOTH
question, and previously the UI looked finished while a correction might still
arrive.

Time from submit to the first visible sign of work: **~80 s → under 1 second.**

### 6. Breakdown

Above.

---

## Hardware reality — read this before expecting more

**Everything below is a floor set by the CPU, not by the code.**

Measured on this machine: **9.0 tokens/sec generation, 44 tok/s prompt read**, no
CUDA GPU. That single number sets the limit:

- A 300-token answer **cannot** take less than ~33 s to generate.
- Reading 2,800 tokens of retrieved context **cannot** take less than ~64 s.
- One 7B generation already saturates all 16 cores, so a second concurrent
  request does not run in parallel — it splits the same silicon.

**What the remaining time is spent on, after this work:**

| | median | Reducible in software? |
|---|---|---|
| Synthesis | 78.5 s | **No.** This is the answer being written, one token at a time. |
| Verification (RAG/BOTH) | 62–95 s | Partly — it re-reads the full evidence. |
| SQL generation | 7.5 s | Marginally. |
| Router | 0.4 ms | **Done.** |
| Retrieval | 0.15 s | **Was never the problem.** |

**So: a descriptive question will still take 90–150 seconds on this hardware, and
no further prompt engineering will change that.** I have removed essentially all
of the overhead that was not raw token generation. What remains *is* raw token
generation.

**The honest options from here are hardware, not code:**

1. **A 24 GB GPU** takes generation from 9 tok/s to ~100–140 tok/s. A RAG answer
   goes from ~150 s to roughly 15–40 s. This is the only change that moves the
   floor. (Projected from published 7B benchmarks — **not measured here**, because
   this machine has no GPU.)
2. **`qwen2.5:3b` for synthesis** — roughly 2.5× faster, at a real cost in answer
   quality. The router already uses it, where the task is a four-way choice and
   the quality cost is nil.
3. **`ENABLE_VERIFICATION=false`** — removes 62–95 s from descriptive answers, and
   removes the only check on wrong answers. Not recommended for a system
   answering questions about fees and deadlines.

**What I did not promise:** none of this makes the assistant fast. A SQL question
went from 54 s to 15 s, which is a genuine change in how it feels. A descriptive
question went from ~300 s to ~145 s, which is still too slow to feel interactive.
The gap between those and "fast" is a GPU.

---

## Verification of correctness

| | |
|---|---|
| Backend test suite | **105 passed** (was 80; +25 new) |
| Router accuracy tests | 8, incl. 100%-precision and 97%-coverage floors |
| Verification fast-path tests | 17, **most asserting it declines** |
| Routes before vs after | **7/7 identical** |
| Answers truncated | **0** (max 1,252 chars vs ~3,500 cap) |

## Configuration added

All default to the tuned values; every one can be reverted without a code change.

```
FAST_ROUTER=true                  # false -> always use the LLM router
ROUTER_MODEL=qwen2.5:3b           # was qwen2.5:7b
ROUTER_NUM_PREDICT=80
ROUTER_EMBED_CONFIDENCE=0.62
FAST_VERIFICATION=true            # false -> always use the LLM verifier
FAST_VERIFICATION_MAX_CHARS=700
VERIFY_NUM_PREDICT=400
CORRECT_NUM_PREDICT=600
SQL_NUM_PREDICT=300
SYNTHESIS_NUM_PREDICT=900
```

`FAST_ROUTER=false` and `FAST_VERIFICATION=false` restore the previous behaviour
exactly, which is the intended way to A/B this on real traffic.
