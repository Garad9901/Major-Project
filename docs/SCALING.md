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
