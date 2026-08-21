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

---

# Second pass — 18 August 2026

**Hardware:** unchanged (Intel Core Ultra 9 185H, 16 cores / 22 threads, 31.4 GB
RAM, **no CUDA GPU**). Ollama 0.32.3.
**Method:** the previous pass was benchmarked on 7 hand-picked questions. This
one is measured against **163 real questions** recorded in
`orchestrator.QueryProfile` (`manage.py latency_report`), plus controlled
micro-benchmarks run directly against Ollama's `/api/chat` with the prefix cache
deliberately defeated.

## Read this first: the premise of this pass was wrong

The brief for this work stated a median of **141.6 s**. That number is real but
it is **not the median** — it is question #3 of the 7-question benchmark in the
pass above, a RAG-route descriptive question.

Measured over the last 163 questions actually asked:

| | p50 | p95 | p99 |
|---|---|---|---|
| **End to end** | **28.2 s** | 197.2 s | 248.5 s |
| **Time to first token** | 21.7 s | 141.5 s | 245.6 s |
| **Time to readable answer** | **24.5 s** | 158.3 s | – |

Real traffic is **126 SQL / 26 RAG / 9 BOTH / 2 WEB**, so the median question is
a SQL count, not a descriptive essay. Optimising against 141.6 s would have been
optimising against roughly the 90th percentile while calling it the middle.

## Summary

| | Before | After | |
|---|---|---|---|
| **Median end to end** | 28.2 s | 28.2 s | unchanged |
| **Median time to readable** | 24.5 s | 24.5 s | unchanged |
| **Prompt truncation risk** | **live, silent, security-relevant** | **closed** | — |

**No latency change was shipped in this pass, because none of the candidate
optimisations survived measurement.** What was shipped is a correctness fix that
measurement turned up on the way: prompts were one long answer away from being
silently truncated, and truncation removes the *front* of the prompt, which is
where the prompt-injection defences live.

---

## The one real finding: silent prompt truncation (SECURITY)

`num_ctx` was never set by any agent (`grep -rn num_ctx backend` returned
nothing), so Ollama applied its own default. With no GPU that default is:

```
level=INFO source=routes.go:2054 msg="vram-based default context"
      total_vram="0 B" default_num_ctx=4096
```

**4,096 tokens.** Measured largest single prompt across 300 recorded questions:

| stage | prompt tokens p50 | p95 | **max** | headroom at max |
|---|---|---|---|---|
| **synthesis** | 1,779 | 2,972 | **3,365** | **18%** |
| sql | 1,352 | 1,361 | 1,368 | 67% |
| router | 1,029 | 1,046 | 1,050 | 74% |
| verification | 523 | 1,681 | 2,100 | 49% |

Nothing had truncated **yet** — 0 calls of 331 exceeded 4,096. But synthesis was
already at 82% of the ceiling, and its prompt grows with the retrieved passages.

**What truncation actually does, measured.** An ~11,000-token system prompt
beginning with a canary, sent with `num_ctx=4096`:

```
prompt_eval_count reported: 2050        (the prompt was ~11,000 tokens)
answer: "It seems there might be a repetition or misunderstanding in your
         question. You mentioned 'secret canary token' but provided
         information about the faculty develo..."
```

The model never saw the canary. **Ollama silently discards the front of the
prompt** — and the front of every synthesis prompt is the system prompt,
including the entire `# UNTRUSTED CONTENT` section that defends against the
injection attack recorded in `synthesis_agent/llm_client.py`. A long enough set
of retrieved passages would therefore have disarmed the injection defences
without raising an error, logging anything, or changing how the answer looked.

**Cost of fixing it: none, measured.**

| num_ctx | prefill tok/s | generation tok/s |
|---|---|---|
| 4,096 | 29.6 | 7.85 |
| **8,192** | **29.0** | **8.10** |

(n=2 each, alternating order.) The difference is inside run-to-run noise.

That first benchmark defeated the prefix cache, which is **not** what a real
call looks like. Re-measured on the common path — the real ~1,400-token
synthesis system prompt already warm, then a fresh per-question body, again
alternating, n=3:

| num_ctx | fresh-body prefill (median) | range |
|---|---|---|
| 4,096 | 140,182 ms | 140,092–143,739 |
| **8,192** | **131,030 ms** | 113,973–133,459 |

**0.93×** — if anything slightly faster, and the ranges do not overlap. Doubling
the context window costs nothing on this deployment.

`num_ctx=8192` is now set explicitly in `common/ollama.py` for every chat call.

**One-off cost, worth knowing about.** Changing `num_ctx` makes Ollama reload
the model at the new size, which discards the prefix cache. The first question
after this change took **110.9 s** (synthesis prefill 68.4 s) because it paid
full prefill on a cold cache. The next three were 10.1 s, 34.6 s and 32.4 s with
correct answers (2,073 / 3,053 / 1,046), i.e. straight back to normal. Expect
one slow question after any restart that changes this value.

---

## Measured and rejected

### 1. Model swapping between agents — DISPROVEN

`OLLAMA_MAX_LOADED_MODELS` is unset, and the pipeline uses three models
(`nomic-embed-text`, `qwen2.5:3b`, `qwen2.5:7b`). The hypothesis was that Ollama
was evicting and reloading one on every request.

It is not. Querying `/api/ps` between calls:

```
=== resident at start === ['nomic-embed-text:latest']
synthesis      ... resident=['qwen2.5:7b', 'nomic-embed-text:latest']
router 3b      ... resident=['qwen2.5:3b', 'qwen2.5:7b', 'nomic-embed-text:latest']
=== resident at end === ['qwen2.5:7b', 'qwen2.5:3b', 'nomic-embed-text:latest']
```

All three stay resident together. The comment in `docker-compose.yml` asserting
this was correct. `load_duration` is ~250 ms on every warm call, which is
bookkeeping, not a 4.7 GB reload — the genuine cold load is **16.4 s** for the
7B and **11.0 s** for the 3B, and it happens once.

**No change made.** Setting `OLLAMA_MAX_LOADED_MODELS` explicitly would pin an
assumption that is already holding, at the cost of a knob that can later be set
wrong.

### 2. Prefix caching is already working, and is load-bearing

Same synthesis-shaped prompt, three times, then interleaved with other models:

| call | prompt tokens | prefill | rate |
|---|---|---|---|
| synthesis, cold | 1,933 | 72,478 ms | 27 tok/s |
| synthesis, repeat | 1,933 | **229 ms** | **8,449 tok/s** |
| synthesis, repeat | 1,933 | **175 ms** | 11,033 tok/s |
| after a `nomic` embedding call | 1,933 | 279 ms | 6,940 tok/s |
| after a `qwen2.5:3b` call | 1,933 | 251 ms | 7,691 tok/s |
| after a *different* 7B system prompt | 1,933 | 495 ms | 3,903 tok/s |

The cache survives interleaving with other models **and** with a different
prompt on the same model. The message-ordering audit found nothing to fix: every
`llm_client.py` already puts the stable system prompt first and the variable
text last, and the two that carry conversation history (`router_agent`,
`sql_agent`) already document why history goes in the *user* message rather than
the system prompt.

This also explains an apparent contradiction in the recorded data — synthesis
appears to read at 117 tok/s while the SQL agent reads at 1,397 tok/s on the
same model. Neither is a real rate. `prompt_eval_count` reports the **whole**
prompt while `prompt_eval_duration` covers only the **uncached** part. The true
figure is one number:

> **Uncached prefill on this CPU is ~26–33 tok/s. Generation is ~7.4–8.2 tok/s.**

At p50, synthesis reads 1,779 tokens in 15.1 s. At 29 tok/s that is **~380
tokens actually evaluated** — the ~1,400-token system prompt is served from
cache. The two numbers agree to within the noise.

**No change made.** This is already optimal; there is nothing to reorder.

### 3. Verification blocking the user — ALREADY FIXED, no work needed

The brief asked for verification to be moved off the critical path so the user
can read the answer while it runs. It already is, and has been since the pass
above.

`orchestrator/service.py` streams synthesis tokens to the client and only then
emits `stage: verifying`; `frontend/src/components/Chat.jsx` renders the
streamed text and shows "Checking the answer against the records…" beneath an
answer that is already fully readable.

Measured over 137 uncached answers:

| | p50 | p95 |
|---|---|---|
| Time to readable answer (synthesis ends) | **24.5 s** | 158.3 s |
| End to end (`done` event) | 30.0 s | 197.2 s |
| **Verification tail, after readable** | **0.1 s** | 41.7 s |

Verification is **0.2% of the p50 request**, because the no-LLM fast path takes
81 of 137 answers. The 62.3 s figure in the brief is the RAG-route case, which
is 26 of 163 real questions.

**No change made.** Restructuring this would have rewritten a working feature to
buy a median improvement of 0.1 s.

### 4. Thread count — a 1.47× "win" that was measurement drift

`num_thread` was never set. A sweep on an uncacheable ~2,080-token prompt
suggested a large win:

| threads | 4 | 6 | 8 | 11 | **14** | 16 | 22 (default) |
|---|---|---|---|---|---|---|---|
| prefill tok/s | 16.5 | 18.6 | 18.7 | 21.4 | **27.4** | 27.0 | 18.6 |

14 threads looked 1.47× faster than the default. **It is not.** That sweep ran
each configuration once, in sequence, so slow drift over the run was
indistinguishable from the variable being tested. Re-run with the two
configurations **alternating**, three times each:

| threads | prefill tok/s (median, range) | generation tok/s |
|---|---|---|
| default (22) | 29.3 (28.7–29.7) | **8.16** |
| 14 | **32.8** (30.1–33.1) | 7.80 |

The real effect is **1.12× on prefill and −4% on generation**, worth roughly
1.5 s of a 28 s request. Note also that the *default* configuration measured
18.6 tok/s in the first sweep and 29.3 tok/s in the second — **the machine
drifts by more than the effect being measured.**

**Not shipped as a default.** `OLLAMA_NUM_THREAD` exists in `common/ollama.py`
and defaults to `0`, meaning "leave it to Ollama". Set it to 14 to take the
~1.12×; the evidence is three alternating pairs, which is thin.

### 5. SQL/RAG parallelism, `num_predict` caps, flash attention, `q8_0` KV

Unchanged from the pass above; all previously measured, none re-tested. Flash
attention plus `q8_0` KV cache remains **rejected** — 1.76× worse on this
CPU-only deployment.

---

## The synthesis model: your decision, with the data

`SYNTHESIS_MODEL` is already a separate env knob. `VERIFICATION_MODEL` is
**already `qwen2.5:3b`** and has been since the previous pass — that half of the
brief's item 4(b) was done, and the notes in `orchestrator/verification.py`
record why.

So the only open question is synthesis. Both runs used
`manage.py run_experiment --configs full` over the 10 ground-truth pairs in
`experiments/fixtures/sample_qa.json`, scored with `experiments/similarity.py`.
Everything else was held constant.

### Raw model speed (micro-benchmark, prefix cache defeated, alternating, n=2)

| | prefill tok/s | generation tok/s |
|---|---|---|
| `qwen2.5:7b` | 26.1 | 7.38 |
| `qwen2.5:3b` | **55.2** | **12.64** |
| | **2.12×** | **1.71×** |

### End-to-end quality and latency

| question | 7B sim | 3B sim | 7B | 3B |
|---|---|---|---|---|
| How many credits is the Operating Systems course worth? | 0.734 | 0.680 ✗ | 132.2 s | 41.2 s |
| What does the Database Systems course cover? | 0.953 | 0.885 ✗ | 24.6 s | 19.7 s |
| Which department offers Organic Chemistry? | 0.891 | 0.891 | 33.0 s | 20.4 s |
| When was the English department established? | 0.722 | 0.733 | 18.5 s | 13.4 s |
| Who teaches Machine Learning Fundamentals? | 0.768 | 0.912 ✓ | 60.6 s | 40.7 s |
| Tuition fee for B.Tech Computer Science? | 0.896 | 0.880 | 35.6 s | 22.3 s |
| Prerequisites for Machine Learning Fundamentals? | 0.792 | 0.818 | 101.6 s | 24.3 s |
| When is the final exam for Database Systems? | 0.591 | 0.443 ✗ | 20.1 s | 13.2 s |
| Topics covered in Linear Algebra? | 0.941 | 0.909 | 24.1 s | 28.9 s |
| How long is the M.Tech Computer Science program? | 0.787 | **0.388** ✗ | 23.6 s | 15.7 s |
| **mean similarity** | **0.807** | **0.754** | | |
| **median similarity** | 0.790 | **0.849** | | |
| **harness accuracy** | **70%** (7/10) | 60% (6/10) | | |
| **mean latency** | **47.4 s** | **24.0 s** | | **1.98×** |

✗ = 3B materially worse (>0.05), ✓ = materially better. **Worse on 4/10, better
on 1/10, comparable on 5/10.**

### Recommendation: keep `qwen2.5:7b`. Confidence: moderate.

The trade is **1.98× faster for −0.053 mean similarity**, and on the face of it
that looks like a good deal. Three things argue against taking it:

1. **The median gets better while the tail gets much worse.** 3B's median
   similarity is actually *higher* (0.849 vs 0.790). The mean falls because of
   outliers — most starkly "How long is the M.Tech Computer Science program?",
   0.787 → **0.388**. That question returned **zero SQL rows**, so it is a
   "the records don't cover this" case, and those are exactly where this
   system's worst historical defects have lived: the false-absence bug that
   took four attempts to fix, and the invented "Dr. Jane Smith". A model that
   is fine on average and bad on empty results is badly matched to this
   pipeline.

2. **Neither number is interactive.** 47 s and 24 s are both "go and do
   something else" latencies. Halving a wait nobody is sitting through does not
   change the product, so there is little to weigh against a quality risk.

3. **n=10.** One question is ten accuracy points. 70% vs 60% is one question.
   This sample cannot distinguish those with any confidence, which is why the
   continuous similarity scores are reported alongside — and why the confidence
   here is "moderate", not "high".

**What would change my mind:** a larger fixture set (50+ pairs, weighted towards
the faculty-development questions real users actually ask, since the current
fixtures are all course/program questions) showing 3B holding up on the
zero-row and no-data cases. If you want that, it is a ~2 hour run and I would
want the fixtures reviewed first.

**To try it yourself, no code change:** set `SYNTHESIS_MODEL=qwen2.5:3b` in
`.env` and restart the backend. Everything above is reproducible with:

```
docker exec -e SYNTHESIS_MODEL=qwen2.5:3b backend \
  python manage.py run_experiment --configs full --tag syn3b
```

---

## Where the floor is

**The remaining cost is physics, and the only real lever is hardware.** The
numbers behind that claim:

| | measured |
|---|---|
| Uncached prefill, `qwen2.5:7b` | **26–33 tok/s** |
| Generation, `qwen2.5:7b` | **7.4–8.2 tok/s** |
| Cold model load, 7B / 3B | 16.4 s / 11.0 s (once) |
| Prefix-cache hit rate, synthesis system prompt | ~1,400 of ~1,780 tokens |

A p50 SQL question spends **28.2 s**, and it decomposes almost entirely into
those two rates:

| | p50 | what it is |
|---|---|---|
| SQL agent | 3.7 s | one SELECT generated at 7.8 tok/s |
| **Synthesis prefill** | **15.1 s** | **~380 uncached tokens at ~26 tok/s** |
| Synthesis generation | ~3.0 s | ~16 tokens at 7.2 tok/s |
| Verification | 0.05 s | the no-LLM fast path, 81 of 137 answers |
| Everything else | ~1 s | cache lookup, routing, retrieval, plumbing |

**The single largest cost in the system is synthesis prefill: 15.1 s, 54% of the
median request, and it is ~380 tokens of prompt that cannot be cached.**

Those ~380 tokens are the per-question part of the prompt: the question, the
route, the SQL rows, the retrieved passages, and the ~170-token
`_POST_CONTENT_REMINDER`. That reminder is *stable text* and would be free if it
sat in the system prompt — but it exists precisely because it must be the
**last** thing the model reads, and moving it re-opens the injection hole it was
added to close (see `synthesis_agent/llm_client.py`). So roughly **6 s per
question is a security control that structurally cannot be prefix-cached.** That
is a real cost, honestly the most interesting remaining target, and not one I
would touch without an injection test gating it.

### What actually moves it

| lever | effect | cost |
|---|---|---|
| **A 24 GB GPU** | generation 9 → 100–140 tok/s, prefill ~20× | money. *Projected from published 7B benchmarks, not measured — this machine has no GPU.* |
| `SYNTHESIS_MODEL=qwen2.5:3b` | **1.98× measured** | −0.053 mean similarity, worse on empty-result questions |
| Shorten `_POST_CONTENT_REMINDER` | ~6 s of the 28 s p50 is at stake | re-opens a proven injection vector unless gated by a test |
| Fewer RAG chunks (`RAG_TOP_K=5`) | untested; ~600 tokens ≈ 20 s on RAG questions | untested quality cost |
| `OLLAMA_NUM_THREAD=14` | 1.12×, ~1.5 s | thin evidence (n=3), machine-specific |

**Nothing in software gets a descriptive question below about 90 s on this
hardware, and nothing gets a simple count below about 20 s.** The honest summary
is the same as the previous pass reached, now with better numbers behind it: the
overhead has been removed, and what is left is a 7B model reading and writing
tokens on a CPU.

---

# Production correction — 21 August 2026

**The 18 August conclusion on `num_thread` was right for development and
useless for production.** Recording it here because the failure mode is the
interesting part, not the number.

That pass measured `num_thread` on the development stack and found 1.12x —
marginal, thin evidence, not worth hardcoding a core count. So it shipped
defaulting to `0` ("leave it to Ollama"). That reasoning was sound and the
conclusion was wrong, because **development has no CPU limit and production
does.**

`docker-compose.prod.yml` caps ollama at `OLLAMA_CPU_LIMIT` (4.0). A docker CPU
limit is a **quota, not a core count**: `nproc` inside the container still
reports all 22 host threads. llama.cpp therefore spawned 22 threads to share
4 CPUs' worth of quota.

Measured on the production stack, same request, only this value changed:

| `num_thread` | wall | generation |
|---|---|---|
| **4** (matches the cap) | **19.3 s** | **3.73 tok/s** |
| default (22) | 201.9 s | **0.11 tok/s** |

**34x.** At the default, every question exceeded `OLLAMA_READ_TIMEOUT=240` and
users got "The AI service is temporarily unavailable". Proven to be Ollama
rather than the application by making a **direct** `/api/chat` call that
bypassed Django, gunicorn and Caddy entirely — it timed out identically.

`OLLAMA_NUM_THREAD` must equal `OLLAMA_CPU_LIMIT`. `generate_secrets.sh` now
writes it, and `verify_deployment.sh` fails the deployment if the effective
value is unset or exceeds the container's cgroup quota.

### What this says about the earlier measurements

Every number in the 18 August section was taken without a CPU limit, so the
**absolute** figures there describe development, not production. The relative
findings (prefix caching is load-bearing; verification is already off the
critical path; the premise median was the 90th percentile) are unaffected.

But the honest summary is harsher than "one setting was wrong": **a variable
that development cannot express was the difference between working and not.**
Any future latency work must be re-measured under the production resource
limits before its conclusion is trusted.

### Production capacity, so far

At 4 CPUs the measured generation rate is **3.73 tok/s**, against 7.4–8.2 tok/s
in development. Roughly half. A simple SQL question measured **48 s** end to end
over TLS through gunicorn once warm. The concurrency figure and the hardware
requirement that goes with it are **not yet measured** — see
FINAL_DEPLOYMENT_REPORT.md for what remains.
