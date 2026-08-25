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

**3. The 11-CPU generation figure is an OUTLIER, and its cause is not yet
established.** Median 3.41 tok/s against 7.04 at 8 and 7.69 at 16, with a 2.7×
spread and a worst case of 2.06.

> **RETRACTION.** An earlier version of this section attributed the dip to
> E-core gating — llama.cpp splitting work evenly and waiting for the slowest
> thread. **That explanation is wrong and does not survive this table.**
>
> The hypothesis was suggested during review and I recorded it without checking
> it against the data. Two problems:
>
> 1. **Gating cannot produce a dip and a recovery.** Even-split gating gives
>    time ≈ (work / N) × slowest-thread-factor. Adding threads on slower cores
>    reduces per-thread work while the slow factor stays roughly fixed, so
>    throughput rises with diminishing returns. It is monotonic. It cannot fall
>    at 11 and recover at 16.
> 2. **The direction is inverted.** 16 CPUs reaches into the two low-power
>    E-cores, the slowest on the die; 11 touches only P and standard E cores.
>    Gating therefore predicts 16 < 11. Measured: 16 = 7.69, 11 = 3.41. The
>    mechanism predicts the opposite of the observation.
>
> A mechanism that fails its own data is worse than no mechanism, because it
> stops the question being asked.

**Two candidates remain, and they are distinguishable:**

- **Sampling.** A 2.7× spread with a worst case of 2.06 is bimodal. A median of
  three draws from a bimodal distribution is not a point estimate — it is
  whichever mode happened to take two of three. The same objection applies to
  the 4-CPU point, which also spread 2.7×.
- **Topology.** 11 is the only ODD allocation in the sweep. 4, 6, 8 and 16 all
  align to SMT sibling pairs; 11 cannot. If `cpuset-cpus 0-10` splits a sibling
  pair, that is a topological artefact with nothing to do with core classes.

See "Discriminating the 11-CPU outlier" below for the experiment.

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
bandwidth-bound above it, with a ceiling roughly half the predicted band.

**A second retraction, on WHY the level is lower.** An earlier version of this
paragraph blamed "soldered laptop LPDDR5, slower than the desktop dual-channel
DDR5 the estimate assumed". That is simply false: the 185H runs LPDDR5x at
around **120 GB/s theoretical, HIGHER** than the desktop dual-channel DDR5 the
estimate was based on. The explanation was plausible-sounding and backwards.

Two things that do fit:

- **Achieved bandwidth is not theoretical bandwidth.** Real-world sustained
  throughput is typically 50–60% of the rated figure, which brings ~120 GB/s
  down to ~60–70 GB/s and the predicted ceiling down with it.
- **The 4.7 GB weights-only figure is incomplete.** At `num_ctx=8192` the KV
  cache is read alongside the weights on every token, so the per-token traffic
  is larger than the model file — and the estimate ignored it entirely.

Both push the ceiling down from 11–14 towards the ~7 measured, without needing
the memory to be slow.

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

**`OLLAMA_CPU_LIMIT=8` is the defensible default on a machine of this shape**,
for three reasons that are established:

1. **It is past the knee at 6**, so it gets the 2.1× prefill step rather than
   sitting below it.
2. **It has the tightest spread of the post-knee points** — 1.10× on prefill,
   1.17× on generation. A reproducible number is worth more than a marginally
   higher unreproducible one.
3. **It leaves 14 of 22 threads for everything else**, against measured headroom
   of under 3.4% of one core and ~350 MB.

Deliberately NOT justified as "avoiding the unstable 11-CPU region". That claim
is not established — see the retraction above. 8 would be the right choice on
these three grounds even if 11 turns out to have been a sampling artefact.

This is a recommendation about *this* curve, on this machine. Run
`scripts/capacity_test.sh` on the target server.

---

## Discriminating the 11-CPU outlier — 22 August 2026

**Verdict: topological, not sampling.** The retracted E-core explanation is
replaced by a measured one.

**Method.** Allocations 10, 11, 12 — 11 is the only odd point, its neighbours
are both SMT-aligned. **8 samples each**, because a 2.7× spread does not support
a median of three. Container started once per allocation with every call
carrying a unique prefix, so the prefix cache never hits and each sample
measures compute rather than cache.

| CPUs | n | prefill median | range | generation median | range | spread |
|---|---|---|---|---|---|---|
| 10 | 8 | 33.0 | 28.3–35.2 | **6.91** | 1.94–7.44 | 3.8× |
| **11** | 8 | 34.2 | 32.5–35.0 | **3.04** | 2.31–5.56 | 2.4× |
| 12 | 8 | 35.7 | 33.8–36.4 | **7.92** | 7.23–8.19 | 1.1× |

### It is not sampling

If the 11-CPU figure were a bimodal distribution badly summarised by three
draws, more samples would surface the high mode. They do not:

- **0 of 8 samples at 11 exceed 6.0 tok/s.**
- **15 of 16 samples at 10 and 12 do.**
- 11's best sample (5.56) sits below its neighbours' median (7.38). The
  distributions do not overlap at the top.

Eight consecutive draws landing in the low mode is not a summary artefact.

### It is specific, in two ways that matter

**Only generation is affected.** Prefill at 11 is 34.2 median with the tightest
range of the three (32.5–35.0) — indistinguishable from its neighbours. Whatever
degrades generation leaves prompt reading alone.

**Only the odd allocation is affected.** Both even neighbours are clean, and 12
is the best point measured anywhere in either sweep.

11 CPUs is the only allocation in either sweep that cannot be expressed as whole
SMT sibling pairs; `--cpuset-cpus 0-10` necessarily leaves one logical CPU whose
sibling is outside the set. That is consistent with the observation and is
**stated as consistent, not proven** — confirming the mechanism would need
per-thread placement data the VM does not expose.

### One honest complication

The 10-CPU run produced a single low sample (1.94) in 8. So the low mode is not
exclusive to odd allocations — it is merely **rare** there (1 in 8) and
**universal** at 11 (8 in 8). Recorded rather than smoothed away: it means this
is a tendency, not a switch, and it is another reason no figure from this
machine should be quoted as a specification.

### Consequence for the recommendation

**12 CPUs is the best point measured in either sweep** — highest generation
(7.92), highest prefill (35.7) and by far the tightest spread (1.1×).

The shipped default stays **8** for now, and the reason is that the comparison
is not like-for-like: 8 rests on **n=3** while 12 rests on **n=8**. 8's
generation spread was 1.17×, under the 1.5× threshold at which a median of three
stops being meaningful, so its figure is defensible — but it has not been
measured to the same standard as 12.

**If the number matters on your hardware, run the sweep at equal n.** On this
machine the evidence currently points at 12 rather than 8, and the honest
statement is that the two have not been compared fairly.

---

## Equal-n comparison, and why the answer is a rule rather than a number

`OLLAMA_CPU_LIMIT=8` had been chosen on **n=3**. That was not a finding of
stability — it was the absence of a measurement. Having observed a slow mode in
**1 of 8** samples at an even allocation, three samples miss it **67%** of the
time, `(7/8)³`. So the shipped default rested on a run too short to see the
failure mode we had just demonstrated exists.

Re-measured at **n=8**, all four allocations:

| CPUs | n | prefill median | gen median | gen range | spread | samples < 6.0 |
|---|---|---|---|---|---|---|
| 8 | 8 | 32.3 | 6.30 | 5.19–6.63 | 1.28× | **2/8** |
| 10 | 8 | 33.0 | 6.91 | 1.94–7.44 | 3.84× | 1/8 |
| 11 | 8 | 34.2 | 3.04 | 2.31–5.56 | 2.41× | 8/8 |
| **12** | 8 | **35.7** | **7.92** | 7.23–8.19 | **1.13×** | **0/8** |

**8 was not clean.** At n=8 its spread is 1.28× with two samples below 6.0 —
the original 1.17× over three draws was under-sampling, exactly as predicted.

**12 wins on every axis**: highest prefill, highest generation (**+25.8%** over
8), tightest spread, and the only allocation with **no** low sample in 8 draws.

### But 12 is not the recommendation, because a literal is the wrong shape

Everything distinctive in this data — the knee at the P-core count, the
odd-allocation degradation, the low mode — is an artefact of a **hybrid laptop
chip behind a synthetic VM topology**. A college on a Xeon or EPYC has
homogeneous cores and none of it applies. On a 64-core server both 8 and 12 are
absurd; on a 4-core box both are impossible.

**The durable finding is a rule:**

> Past the physical core count, additional cores buy almost nothing for
> generation. Size on **memory bandwidth**, not cores.

`scripts/generate_secrets.sh` now derives `OLLAMA_CPU_LIMIT` on the machine it
runs on: target the physical core count, leave two logical CPUs for the rest of
the stack, prefer an even allocation, floor at 4 with a warning. 12 remains only
as the fallback literal in `docker-compose.prod.yml`, for the case where nothing
was derived.

### A worked example of why you run the test rather than trust the rule

On this machine the derivation produces **10**, while measurement prefers **12**.

The rule is not wrong; **it is being fed a lie about the hardware**. `lscpu`
inside the VM reports 11 physical cores — a synthetic figure. The real host has
16 (6 P + 8 E + 2 LP-E). The derivation targets 11, rounds to even, and lands on
10, which measured a 3.84× spread.

On real server hardware `lscpu` reports true topology and the rule should land
correctly. This machine is precisely the case it cannot handle — which is the
argument for `scripts/capacity_test.sh` rather than any formula:

**derive a starting point, then measure it.**

---

# `LLM_QUEUE_TIMEOUT=25` — where it came from — 25 August 2026

The value governs how long a queued question waits for the single LLM slot
before the user is told the assistant is busy. With `LLM_MAX_CONCURRENCY=1`,
capacity is queueing rather than parallelism, so this constant — not the
hardware — sets how many people a server can serve.

## It has never been edited

```
$ git log -L 55,55:backend/orchestrator/concurrency.py
7f5ef68 chore: place the College Assistant under version control
+QUEUE_TIMEOUT_SECONDS = float(os.getenv("LLM_QUEUE_TIMEOUT", "25"))
```

One commit: the initial one. **25 has been the default since the repository
existed and was never changed.**

This also disposes of a premise worth correcting explicitly, because it was
believed for a while during this work: that the default had at some point been
120 and was later lowered. It never was. `PRODUCTION_AUDIT_REPORT.md` records a
question refused with *"llm queue timeout after 120s"*, which is a real sighting
but of the auditor's own shell environment, not of a shipped default. Nothing in
the repository has ever defaulted to 120.

## But it was not arbitrary either — and that is the actual finding

The constant carries a justification, in `backend/orchestrator/concurrency.py`:

> Long enough to absorb the tail of one in-flight answer, short enough that a
> refusal arrives while the user is still paying attention. Measured answers are
> 19-22s warm, so 25s covers roughly one full answer ahead in the queue.

The reasoning is sound and the intent is right. **The number it rests on is
one this project has since measured to be wrong.** `docs/LATENCY.md` puts the
end-to-end p50 at **28.2 s** over 163 real questions — against the 19–22 s the
comment assumes:

| | source | n |
|---|---|---|
| comment's assumption | 19–22 s warm | a handful of warm single questions |
| **measured p50** | **28.2 s** | **163 questions** |
| measured p95 | 197.2 s | |

So the comment's own stated goal — *"covers roughly one full answer ahead in
the queue"* — **is not met by the value it justifies.** 25 < 28.2. The second
person in the queue is turned away before the answer ahead of them has reached
its median completion, let alone its tail. The timeout does the opposite of
what its comment says it does.

## And the correction was already measured, then never applied

The 50-user load test in this same document found the same thing from the other
direction, and recommended a fix:

| | served | busy | throughput |
|---|---|---|---|
| cache only | 2 | 48 | 2.4/min |
| + coalescing | 21 | 29 | 18.4/min |
| **+ tuned queue timeout** | **50** | **0** | **28.1/min** |

> "with coalescing there are only ~5 real jobs, so the 25s queue timeout was
> mistuned and was refusing leaders that would have succeeded.
> `LLM_QUEUE_TIMEOUT=120`."

That recommendation reached **no configuration that ships**. Verified today:

| location | value |
|---|---|
| `backend/orchestrator/concurrency.py:55` | `25` |
| `.env.example:111` | `25` |
| `docker-compose.prod.yml:127` | `${LLM_QUEUE_TIMEOUT:-25}` |

(`docs/SCALING.md:146` shows `LLM_QUEUE_TIMEOUT=30`, but that is inside the
vLLM-on-GPU migration block, where answers are 10–30× faster. It is a different
hardware context, not a fourth contradictory value.)

**This is the backup-crontab failure mode again**: a finding that was measured,
written down, and never made it into the configuration. From inside the running
system a documented-but-unapplied fix and a forgotten one are the same thing.
Two occurrences make it a pattern worth a release-gate check — *does every
recommendation in the docs correspond to a value in a file that ships?*

## What is NOT being changed here, and why

**The default stays at 25 in this commit.** The evidence for 120 is a single
load test of a *coalescing-friendly* shape — 50 users over 5 common questions,
where only ~5 requests are real generations. That is the favourable case. It
does not establish 120 for a room asking different questions, and raising a
timeout to a value where a user waits two minutes for a refusal is a product
decision about patience, not an engineering one.

What the evidence does establish is that **25 is not defensible on its stated
reasoning**, whatever replaces it.

## The honest state of the measurement

A queue-timeout curve — 25 / 60 / 120 / 180 against users served, rejection
rate and worst-case wait — was started and **is not reported here.** It ran
inside an ephemeral container that was reclaimed with the raw data in it, and
the replacement machine has 2 CPUs against the 12 the run used. It is not
resumable on comparable hardware and is not being reconstructed from memory.

One observation survived, and is recorded as an observation only — **not a
curve, not a capacity figure**, and not to be quoted as either:

> 12 CPUs, 12 simultaneous users, `LLM_QUEUE_TIMEOUT=25`.
> All-distinct questions: **5 of 12 answered**, mean 71 s (range 24–118 s).
> 70 %-repeated questions: **10 of 12 answered**, mean 24 s (range 22–44 s).
>
> Single run at each shape. The all-distinct figure was refused by
> `capacity_test.sh`'s own `MIN_SAMPLES` guard — 5 completions is below the
> floor for a publishable mean — and the spread exceeds 1.5× in both shapes.

Consistent with the argument above, and with coalescing being the dominant
effect at this timeout, but **one run is not evidence** and the difference
between the shapes is exactly what a single sample cannot separate from noise.

`scripts/capacity_test.sh` ships so that a buyer can run this on their own
hardware, which is the only place the answer is meaningful. See
`docs/CAPACITY.md` for the method.
