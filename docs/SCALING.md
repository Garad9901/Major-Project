# Scaling to 50 concurrent users

Copyright (c) 2026 Yash Garad. All rights reserved.

Measured findings and the migration path to a GPU serving layer.

---

## The profile: where the time actually goes

Measured on this machine (Intel Core Ultra 9 185H, 16 cores, 31 GB RAM, **no
CUDA GPU**), one SQL question, models already resident:

| Stage | Time | Share |
|---|---|---|
| verification (LLM) | 5.17s | 27% |
| router classify (LLM) | 3.29s | 17% |
| SQL generate + execute (LLM) | 2.72s | 14% |
| synthesis stream (LLM) | 2.61s | 14% |
| qdrant vector search | 0.18s | 1% |
| **db: introspect schema** | **0.02s** | 0.1% |
| **db: connect** | **0.01s** | 0.0% |
| **db: execute agent query** | **0.00s** | 0.0% |

**LLM inference is 72.5% of the pipeline. The database is 0.1%.** Any optimism
about database tuning making this faster is misplaced — there is nothing there
to win.

Embedding measured 5.02s in that first profile, but that was a **cold model
load**; warm it is **0.04s**. Which leads to the biggest finding of all.

---

## Finding 1: model eviction dominated everything

Ollama's default `keep_alive` is **5 minutes**. After that it unloads the model,
and the next question pays a full reload from disk. Same question, same machine:

| | first token | total |
|---|---|---|
| warm (resident) | 6.96s | **13.46s** |
| cold (evicted) | 225.69s | **263.44s** |

**19.6× slower.** On a lightly-used server — which is what this is outside peak
hours — five minutes of quiet is normal, so *most* questions paid it. This
single environment variable was worth more than every other change combined:

```
OLLAMA_KEEP_ALIVE=-1
```

**Cost: RAM.** All three models stay resident (~7.7 GB), so
`OLLAMA_MEMORY_LIMIT` was raised from 8g to 12g. If the server cannot spare
that, set `OLLAMA_KEEP_ALIVE=5m` and accept slow first questions.

---

## Finding 2: a cache alone does nothing for simultaneous questions

50 users drawing from 5 common questions, semantic cache enabled:

```
served 2    busy 48    throughput 2.4/min
```

Every user looked up the cache *before* the first answer had been generated, so
every one of them missed. This is a **cache stampede**, and no similarity
threshold fixes it.

The fix is **request coalescing**: the first caller of a question generates, and
everyone else asking the same question waits on that result instead of queuing
for their own LLM slot. 50 users over 5 questions becomes 5 generations and 45
waiters.

| | served | busy | throughput |
|---|---|---|---|
| cache only | 2 | 48 | 2.4/min |
| **+ coalescing** | 21 | 29 | 18.4/min |
| **+ tuned queue timeout** | **50** | **0** | **28.1/min** |

The last step matters: with coalescing there are only ~5 real jobs, so the 25s
queue timeout was mistuned and was refusing leaders that would have succeeded.
`LLM_QUEUE_TIMEOUT=120`.

---

## Finding 3: pooling is about connection limits, not speed

The database contributes 0.03s to a ~13s answer, so pooling wins no latency.
It is required for a different reason:

* `rag_agent_ro` has **CONNECTION LIMIT 10**
* answering one question opened **two** fresh connections (schema + query)

Past ~5 simultaneous questions Postgres refuses with *"too many connections for
role"*. The failure mode is errors, not slowness — which is why the profile
missed it and the load test found it. Now pooled (`ThreadedConnectionPool`,
max 8).

**A caution learned the hard way.** Setting Django's `CONN_MAX_AGE=60` globally
caused an outage under load:

```
psycopg2.OperationalError: FATAL: sorry, too many clients already
```

Django keeps one connection **per thread**, and `runserver` spawns an unbounded
thread per request — 50 users held 50+ persistent connections and exhausted
Postgres's `max_connections`. Persistent connections are only safe when workers
are bounded, so `CONN_MAX_AGE` is now **0 in development** and **60 in
production**, where gunicorn caps concurrency at 1 worker × 4 threads.

---

## Migrating to vLLM

**vLLM was not adopted here, and could not be tested, because this machine has
no CUDA GPU** (Intel Arc integrated graphics; `nvidia-smi` unavailable). vLLM
requires CUDA or ROCm; its CPU backend must be built from source and is not
performance-oriented.

More importantly: **on CPU, batching does not help.** vLLM's continuous batching
extracts throughput from parallel compute a GPU has and a CPU does not. A single
7B generation already saturates all 16 cores; admitting 50 concurrent requests
splits the same cores 50 ways and makes everyone slower. That is why
`LLM_MAX_CONCURRENCY` and `OLLAMA_NUM_PARALLEL` are both 1.

**vLLM is the right move the moment there is a GPU.** On a CUDA host:

```bash
docker run --gpus all -p 8000:8000 \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  vllm/vllm-openai:latest \
  --model Qwen/Qwen2.5-7B-Instruct \
  --max-model-len 8192 \
  --gpu-memory-utilization 0.90
```

Then, because vLLM serves an **OpenAI-compatible** API and Ollama exposes the
same shape at `/v1`, the application change is configuration:

```
OLLAMA_BASE_URL=http://vllm-host:8000
LLM_MODEL=Qwen/Qwen2.5-7B-Instruct
LLM_MAX_CONCURRENCY=32        # a GPU CAN serve these in parallel — measure it
LLM_QUEUE_TIMEOUT=30
```

`backend/common/ollama.py` posts to `/api/chat`; vLLM's endpoint is
`/v1/chat/completions` with `choices[0].message.content` instead of
`message.content`. That is the one code change required, and it is small — but
it is **untested here** and must be verified on the GPU host before rollout.

Keep an embedding server too: vLLM can serve `nomic-embed-text`, or leave Ollama
running solely for embeddings.

**Expected gain, not measured:** GPU inference for a 7B model is roughly 10–30×
CPU for single-stream latency, and continuous batching then serves tens of
concurrent requests at close to single-stream latency. That is what makes 50
genuinely-different questions viable — which, on this hardware, is not.

---

## Honest ceiling on the current hardware

| Scenario | Result |
|---|---|
| 50 users, 50 **different** questions | **1 served, 49 refused** |
| 50 users, 5 **common** questions | **50 served**, mean 58.1s, p95 105.1s |

Coalescing and caching only help when questions **repeat**. For a management
dashboard — where many people look at the same few figures — that is the real
pattern and the system now handles it. For 50 genuinely distinct questions at
once, nothing short of a GPU changes the answer.

---

# CPU allocation sweep — 22 August 2026

**Measured for SHAPE, not as a specification.** See `scripts/capacity_test.sh`
for why no figure from this machine is a specification for yours.

**Method.** `qwen2.5:7b`, identical 2,067-token prompt, `num_predict=40`,
`num_ctx=8192`. Ollama restarted per point with `--cpus N --cpuset-cpus 0-(N-1)`.
`OLLAMA_NUM_THREAD` set to match the allocation at **every** point — a point
measured with a mismatched thread count measures the 34× oversubscription bug,
not the cap. 3 reps each. Production Ollama stopped throughout, so nothing
contended.

**Host caveat, and it is the important one.** The Docker VM presents a uniform
11 cores × 2 threads. The real host is an Intel Core Ultra 9 185H: **6
performance cores, 8 efficiency cores, 2 low-power cores**. `cpuset-cpus` pins
placement *within the VM*; the hypervisor still chooses which physical core each
vCPU lands on. So the P/E asymmetry is present in the results and invisible to
the measurement.

## Prefill — tok/s

| CPUs | rep 1 | rep 2 | rep 3 | **median** | spread |
|---|---|---|---|---|---|
| 4 | 9.6 | 15.3 | 25.7 | **15.3** | **2.7×** |
| **6** | 32.0 | 32.6 | 33.1 | **32.6** | 1.03× |
| 8 | 35.9 | 32.7 | 33.4 | **33.4** | 1.10× |
| 11 | 36.0 | 33.4 | 35.5 | **35.5** | 1.08× |
| 16 | 37.4 | 37.1 | 35.8 | **37.1** | 1.04× |

## Generation — tok/s

| CPUs | rep 1 | rep 2 | rep 3 | **median** | spread |
|---|---|---|---|---|---|
| 4 | 3.01 | 5.16 | 5.97 | **5.16** | 2.0× |
| 6 | 6.64 | 6.64 | 6.20 | **6.64** | 1.07× |
| 8 | 6.12 | 7.04 | 7.18 | **7.04** | 1.17× |
| **11** | 5.61 | 3.41 | 2.06 | **3.41** | **2.7×** |
| 16 | 8.83 | 6.25 | 7.69 | **7.69** | 1.41× |

## What the shape says

**1. The knee is at 6, and 6 is the host's P-core count.** Prefill goes
15.3 → 32.6 tok/s from 4 to 6 CPUs (**2.1×**), then gains only 14% across the
whole range 6 → 16. A knee landing exactly on the performance-core count is
consistent with E-core threads contributing little; it is not proof, because
the VM hides placement.

**2. The shipped default of 4 is the worst point on the curve, and the least
predictable.** Half the prefill throughput of 6, and a **2.7× spread** between
identical runs. It sits below the knee, in the region where results are not
reproducible. This is the same value that produced the 34× oversubscription
failure. It looks inherited rather than derived, and nothing in this data
justifies it.

**3. Generation at 11 CPUs is non-monotonic and unstable** — median 3.41 tok/s,
**worse than 8 (7.04) and worse than 6 (6.64)**, with a 2.7× spread and a worst
case of 2.06. This was predicted: llama.cpp splits work evenly and waits for the
slowest thread, so threads landing on E-cores gate the whole matmul. **Not
re-run to tidy it up** — it is a result, and it is the strongest single argument
that this platform cannot support a defensible capacity figure.

## The bandwidth prediction: half right, and the level is wrong

The prediction was that generation is memory-bandwidth-bound at roughly
**11–14 tok/s** regardless of core count, so throughput would plateau well
before 11 CPUs.

**The plateau is real.** Beyond 6 CPUs generation gains little: 6.64 → 7.04 →
7.69 across 6, 8 and 16 — **+16% for 2.7× the cores**. Prefill, which
parallelises, keeps climbing while generation does not. The two knees are in
different places, exactly as expected.

**The level is not.** The plateau sits at **~7 tok/s, not 11–14**. And the 4→6
jump (5.16 → 6.64) is too large for a purely bandwidth-bound workload. The
honest reading is that generation is compute-bound below ~6 cores and
bandwidth-bound above it, with a ceiling roughly half the predicted band —
plausibly because this is soldered laptop LPDDR5 rather than the desktop
dual-channel DDR5 the estimate assumed.

Recording it as stated rather than adjusting the prediction to fit: the shape
was predicted correctly, the magnitude was not, and **the ceiling is a property
of the memory subsystem that has to be measured per machine.**

**The buyer-facing consequence stands, and it is the useful part:** past the
P-core count, more cores buy almost nothing for generation. Anyone sizing a
server for this workload should be asking about **memory channels and speed**,
not core count — which is not what a hardware spec usually says.

## Recommended allocation

Measured idle cost of every non-inference service, together:

| service | CPU | memory |
|---|---|---|
| postgres | 2.89% | 30 MB |
| redis | 0.41% | 8 MB |
| backend (gunicorn) | 0.02% | 148 MB |
| qdrant | 0.02% | 59 MB |
| caddy / sync_worker / backup | ~0.00% | 102 MB combined |
| **total** | **< 3.4% of one core** | **~350 MB** |

They are I/O-bound and cheap, which is what makes giving inference 18% of the
machine hard to justify.

**`OLLAMA_CPU_LIMIT=8` is the defensible default on a machine of this shape:**
past the knee, avoids the unstable 11-CPU region, and still leaves 14 of 22
vCPUs — four hundred times what the other services were measured using.

This is a recommendation about *this* curve. On a homogeneous server the knee
will be somewhere else and there will be no E-core instability to avoid. Run
`scripts/capacity_test.sh` on the target machine.
