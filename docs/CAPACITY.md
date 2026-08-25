# How many people can this serve?

Copyright (c) 2026 Yash Garad. All rights reserved.

**This document does not contain your capacity figure, and no honest version of
it could.** It contains the method that produces one, a worked example on
hardware that is probably nothing like yours, and the mistakes we made getting
there — because most of them are mistakes you would make too.

---

## Why there is no number in the datasheet

The obvious thing to print is "serves N concurrent users". We do not, because
the figure we could measure is not transferable.

This system was developed on a laptop, inside a Docker VM, on an **Intel Core
Ultra 9 185H** — a hybrid CPU with 6 performance cores, 8 efficiency cores and 2
low-power cores. Inside the VM that asymmetry is invisible: it presents as a
uniform 11 cores × 2 threads, and the hypervisor decides which physical core
each virtual one lands on, differently from one run to the next. A Docker
`cpus:` limit compounds it, because that is a scheduling **quota, not an
affinity** — inference threads migrate across whatever the host offers.

Your server is very likely a homogeneous Xeon or EPYC, where the effect that
dominates our measurements does not exist at all. Publishing our number as your
specification would be a fabrication with a decimal point on it.

**What transfers is the method.** Run `scripts/capacity_test.sh` on the machine
you intend to buy, before you buy it if you can.

---

## What "capacity" means here, and why it is not parallelism

`LLM_MAX_CONCURRENCY` defaults to **1**, because CPU inference cannot genuinely
run two generations at once — admitting two only splits the same cores and makes
both slower. So capacity in this system is **queueing**:

```
users served  ≈  LLM_QUEUE_TIMEOUT / mean_answer_time
```

Three consequences that are easy to get wrong:

* **CPU speed enters only through `mean_answer_time`.** Faster cores raise
  capacity by shortening answers, not by serving more people at once.
* **Raising `LLM_QUEUE_TIMEOUT` raises the number without improving anything.**
  It makes people wait longer before being turned away. A capacity figure quoted
  without its queue timeout is not a specification; it is a choice about
  patience presented as a property of the hardware.
* **Past the physical core count, more cores buy almost nothing for
  generation** — generation is limited by memory bandwidth, not compute.
  Prefill does keep scaling. **When sizing a server, ask about memory channels
  and speed before core count.** See `docs/SCALING.md`.

That is why the script reports **concurrency, mean answer time and queue
timeout together**, and refuses to print one without the others.

---

## The method

```bash
sh scripts/capacity_test.sh                    # defaults: 20 users, 70% repetition
USERS=50 REPETITION=40 sh scripts/capacity_test.sh
USERS=20 SERVER_URL=https://rag.college.edu sh scripts/capacity_test.sh
```

It waits for `/api/health/` to report ready (**not merely up** — a run started
during model warm-up measures model loading), signs in once, then fires two
waves.

### Two load shapes, and you need both

| shape | what it is | what to do with it |
|---|---|---|
| **pessimal** | every user asks a different question. Nothing hits the response cache, nothing coalesces. | **This is the figure to guarantee.** |
| **realistic** | a proportion of users ask the same thing, which is what a college actually produces — during registration or results week most traffic is a handful of questions. | This is what you should expect in practice. |

The realistic shape exists because the semantic cache and the request coalescer
were built for exactly that traffic, and a distinct-only test hides the thing
they do. **The repetition rate is an assumption you are setting, not a
measurement**, and the script prints it next to the result so nobody mistakes
it for one.

### Two guards that will refuse to give you a number

Both were added after we fooled ourselves, in the two different ways it is
possible to fool yourself with a small sample.

* **`MIN_SAMPLES` (default 8).** Below this the figure is refused outright, not
  annotated. Measuring our own hardware, one CPU allocation produced a slow
  outlier in 1 of 8 samples — at that rate **three samples miss it 67% of the
  time** — so a clean, tight range over three draws is not evidence of
  stability, it is the absence of a measurement. We had already shipped a
  default chosen on exactly that basis. A warning next to a number still leaves
  a number to quote, so there is no number.
* **Spread > 1.5×.** The mean is reported as unreliable and you are told to
  quote the range instead. We measured a 2.7× spread between identical runs,
  where a median of three samples was whichever mode happened to win two draws.

---

## Worked example — measured on a laptop VM, which is not a server

**Read that heading again before quoting any of this.** Intel Core Ultra 9 185H,
inside a Docker VM presenting 11 cores × 2 threads, 31 GB RAM, no GPU,
`OLLAMA_CPU_LIMIT=12`, `LLM_MAX_CONCURRENCY=1`, `LLM_QUEUE_TIMEOUT=25`,
12 simultaneous users:

| shape | answered | turned away | mean answer | range |
|---|---|---|---|---|
| pessimal (all distinct) | 5 / 12 | 7 | **refused — 5 < MIN_SAMPLES** | 24–118 s |
| realistic (70% repeat) | 10 / 12 | 0 | 24 s | 22–44 s |

**This is one run at each shape and it is not a capacity measurement.** It is
included to show what the output looks like and what the guards do — the
pessimal mean was refused by the script's own `MIN_SAMPLES` check, and both
shapes exceeded the 1.5× spread threshold. The run that would have replaced it
was lost with the container it ran in, and the replacement machine was too small
to repeat it. **Do not cite these figures as a specification, as a curve, or as
a comparison between the two shapes** — a single sample cannot separate that
difference from noise.

What it does suggest, consistent with the design, is that at a 25 s timeout
coalescing is the dominant effect. That is a hypothesis worth testing on your
own hardware, not a result.

### The CPU allocation in that run was 12, chosen by measurement, where the formula would have said 10

`scripts/generate_secrets.sh` derives `OLLAMA_CPU_LIMIT` from the machine rather
than shipping a literal. On this machine the derivation produces **10**;
measurement preferred **12** on every axis, including being the only allocation
with no low sample in 8 draws.

The rule is not wrong — **it is being fed a lie about the hardware.** `lscpu`
inside the VM reports 11 physical cores, a synthetic figure; the real host has
16. On real server hardware `lscpu` reports true topology and the derivation
should land correctly. This machine is precisely the case a formula cannot
handle, which is the whole argument for the script:

> **Derive a starting point, then measure it.**

`scripts/test_generate_secrets.sh` exercises that derivation against machine
shapes we cannot obtain — dual-socket Xeon, EPYC, no-SMT, missing topology, and
boxes below the floor.

---

## The queue timeout is a product decision, and it is yours

The shipped default is `LLM_QUEUE_TIMEOUT=25`. **State its assumption plainly:**

> The default assumes a student will wait about 25 seconds, seeing nothing
> happen, before being told the assistant is busy.

We do not think that default is right, and `backend/orchestrator/concurrency.py`
says so: the measured end-to-end p50 is **28.2 s** over 163 real questions, so at
25 s the second person in the queue is refused *before the answer ahead of them
reaches its median*. A 50-user load test recommended 120 — but measured only the
coalescing-friendly shape, so it does not establish 120 for a room asking
different things.

It is left at 25 because the right value depends on facts about your users that
we do not have:

* **Students on phones between lectures** will abandon well before 25 s, and a
  fast refusal is kinder than a long wait.
* **Staff at desks** may happily wait two minutes, and refusing them at 25 s
  throws away capacity the server actually has.

Measure your mean answer time with `capacity_test.sh`, decide how long your
users will wait, and set the timeout accordingly. Raising it does not make
anything faster; it converts refusals into waiting.

**A lever we have deliberately not built:** showing queue position and an
estimated wait in the UI. People tolerate a queue far better when they can see
it, which would make a longer timeout genuinely usable rather than merely
longer. It is not implemented, and nothing here should be read as claiming it is.

---

## Method notes: three ways we measured the wrong thing

Recorded because they cost real time, and because anyone building their own
harness will hit at least one of them.

### 1. The instrument reported every success as a failure

`capacity_test.sh` classified results by grepping the SSE stream for `"error"`.
But the `done` event embeds a per-stage timing profile, and every stage of a
**successful** answer records `"error": null`. Run against a healthy server, the
script reported **0 served, every user failed**.

It was caught only because the backend's own `PROFILE` log lines showed answers
completing in ~80 s while the harness insisted 12 of 12 had failed.

> **When the harness and the logs disagree, suspect the harness first.**

This is the worst place for a bug of its kind: a buyer would have concluded
their server could not answer anything. It now classifies on `^event: done`.

### 2. The questions were not answerable, so we measured the error path

The pessimal wave asked *"How many faculty are in department number N of the
survey?"* — but `faculty_development.department` holds plain text
(`'Engineering'`), and **no department number exists anywhere in the schema**.

The model duly invented a `department_id` column, the SQL errored, and
verification escalated to its slowest LLM path (*sql errored → needs
judgement*). Answers took 180–200 s instead of ~30 s. So the pessimal figure —
the one this document tells you to guarantee — was measuring the
invalid-question path, and understating the server several-fold.

The script now draws from a pool of 56 questions over the dataset's real
dimensions, and **refuses to run** if `USERS` exceeds the pool rather than
wrapping around it, because repeated questions coalesce and would quietly turn
the pessimal run into a partly-realistic one.

### 3. The cache answered, and we recorded it as throughput

Distinct questions miss the response cache on a first run — but on the **second**
run of the same script they are all cached. A repeat run reported a **7 s mean**,
which was the cache, not the server.

The pessimal wave now sends `regenerate: true`. The realistic wave deliberately
does **not**: there the cache and the coalescer are the mechanisms under test,
and bypassing them would measure a system nobody is running.

---

## Related

* `docs/SCALING.md` — the CPU allocation sweep, the memory-bandwidth finding,
  and the migration path to a GPU serving layer.
* `docs/LATENCY.md` — where the time in a single answer goes.
* `backend/orchestrator/concurrency.py` — the admission queue itself.
