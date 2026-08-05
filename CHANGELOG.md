# Changelog and Statement of Work

**Work:** College Assistant — A Multi-Agent Retrieval-Augmented Question Answering System
**Author / Copyright Owner:** Yash Garad
**Year of first publication / completion:** 2026
**Language / Platform:** Python 3.12 (Django), JavaScript (React), SQL (PostgreSQL), Docker
**Copyright (c) 2026 Yash Garad. All rights reserved.**

---

> ### ⚠️ Read before filing
>
> The dates in this document were reconstructed from **filesystem modification
> timestamps**, because this project is not under version control and therefore has no
> commit history. Those timestamps all fall on **24 July 2026**, and they record when
> each file was last *written* — not necessarily when the work was conceived, designed,
> or originally authored.
>
> They are reliable evidence of **the order in which components were built**, which is
> what the section below documents. They are **not** reliable evidence of the overall
> development period.
>
> **Replace the dates below with your actual development timeline before submitting.**
> Sections marked `[CONFIRM]` require your input and must not be filed as-is.

---

## 1. Description of the Work

The College Assistant is a self-hosted software system that answers natural-language
questions about a college's institutional records — courses, departments, faculty, fee
structures, room allocations, class schedules, and examination timetables — through a
web-based chat interface.

The distinguishing characteristic of the work is its **multi-agent architecture**. Rather
than passing a user's question to a single language model, the system decomposes the task
across six cooperating software agents, each with a separate responsibility, prompt
design, and failure mode. A question is classified by route, dispatched concurrently to a
structured-data agent and a semantic-search agent, and the results are merged into a
single natural-language answer.

The system operates **entirely offline**. The language model runs locally via Ollama; no
question, record, or fragment of institutional data is transmitted to any external
service. This is a deliberate design constraint of the work, motivated by the privacy
requirements of student and institutional data.

A second distinguishing characteristic is the **layered database security model** built
around machine-generated SQL. Because a language model composes queries that are then
executed against a live database, the work implements four independent enforcement
layers — a restricted PostgreSQL role, session-level read-only enforcement, an abstract
syntax tree validator, and a table allowlist — such that the failure of any one layer
does not permit unauthorized reads or any write whatsoever.

### Original elements claimed

- The six-agent architecture and the orchestration logic that coordinates it
- The prompt designs for query generation, routing, synthesis, and verification
- The SQL safety validator and its four-layer enforcement model
- The incremental change-detection and embedding-synchronisation algorithm
- The graceful-degradation logic that keeps the system answering when a backing
  service fails
- The database schema for institutional records
- The web client, the API design, and the streaming response protocol
- The accompanying documentation

### Not claimed

Third-party frameworks, libraries, container images, and language models. These are
obtained at build time via dependency manifests, are not distributed as part of the work,
and remain under their own licences. See `LICENSE`, Section 4.

---

## 2. Major Components

### Sync Worker — `sync_worker/`
An independent long-running service that keeps the semantic search index consistent with
the relational database. It polls nine institutional tables on a configurable interval,
detects inserts and updates by comparing per-table high-water marks against a persisted
state file, converts changed rows into natural-language text, generates vector embeddings
locally, and upserts them into the Qdrant vector store. It maintains an append-only change
queue as a durable record of processed work, and connects to the database strictly as the
read-only role. Comprises the poller, change-queue writer, watermark state manager, row-to-
text chunker, embedder, vector-store client, and a self-contained pipeline integration test.

### SQL Agent — `backend/sql_agent/`
Translates a natural-language question into a validated, executable PostgreSQL `SELECT`
statement. Introspects the live database schema at query time — so the prompt can never
drift from the privileges actually granted — then submits the question and schema to the
language model, and subjects the returned text to a validation stage before any execution
occurs. The validator parses the output into an abstract syntax tree and rejects anything
that is not a single `SELECT`, contains a write-class keyword token, references a table
outside the allowlist, or fails to parse. It then rewrites the statement to impose a hard
row cap. Every generated query is logged before execution, including rejected ones.

### RAG Agent — `backend/rag_agent/`
Handles descriptive and open-ended questions that structured queries cannot answer. Embeds
the incoming question using the same locally-hosted embedding model the sync worker uses,
performs a similarity search against the vector store, and returns ranked passages with
provenance metadata identifying the source table and row for each result.

### Router Agent — `backend/router_agent/`
Classifies each incoming question to determine which retrieval strategy applies —
structured records, semantic search, or both — so that downstream agents are invoked only
when relevant. Designed to fail safe: an unparseable classification falls back to querying
both sources rather than guessing, and the fallback is recorded.

### Synthesis Agent — `backend/synthesis_agent/`
Merges structured query results and retrieved passages into a single coherent answer
grounded in the supplied evidence. Supports both a blocking mode and an incremental
streaming mode that emits the answer token by token, enabling the client to display text
as it is produced rather than after completion.

### Verification Agent — `backend/verification_agent/`
Checks a synthesised answer against its source evidence, identifies individual claims,
determines whether each is supported, and records the outcome to a persistent verification
log for later analysis. `[CONFIRM]` This agent is currently invoked from the experimental
evaluation harness and is not wired into the live request path.

### Orchestrator — `backend/orchestrator/`
Coordinates the agents into a single request pipeline. Resolves the route, dispatches the
structured and semantic retrieval steps concurrently, and merges the results. Implements
the graceful-degradation policy: when one retrieval source is unavailable the system
answers from the other and appends a plain-language notice explaining the limitation,
raising an error only when no usable source remains. Also implements input sanitisation
and the server-sent-events streaming protocol.

### Supporting subsystems
- **`backend/academics/`** — the institutional data model and its migrations; the
  idempotent read-only-role provisioning command; the demonstration dataset loader.
- **`backend/accounts/`** — session-based authentication, staff-only authorisation, and
  per-user rate limiting.
- **`backend/audit/`** — a persistent audit trail recording every question, the route
  taken, the generated SQL, the final answer, latency, and prompt-injection indicators.
- **`backend/health/`** — separate liveness and aggregate-readiness endpoints, plus a
  command that verifies the read-only lockdown by attempting a write and confirming
  rejection.
- **`backend/experiments/`** — an evaluation harness measuring answer similarity against
  a reference question-and-answer set, and a concurrent load-testing tool.
- **`frontend/`** — the React chat client, including streaming response handling.
- **Deployment** — Docker Compose orchestration of all services and an HTTPS reverse
  proxy terminating TLS.

---

## 3. Development Record

*Ordering is established by filesystem timestamps; see the notice at the top of this
document regarding the reliability of the dates themselves.*

### Phase 1 — Foundation
Django project structure, service containerisation, React client scaffold, and the
institutional data model with its initial migration. Health-check endpoints and the
read-only role verification tool were established at this stage, before any agent was
built, so that the security model preceded the code it constrains.

### Phase 2 — Sync Worker
The incremental synchronisation pipeline: watermark-based change detection, the durable
change queue, row-to-text conversion, local embedding generation, vector-store upsert, and
an end-to-end pipeline test exercising the real components without mocking.

### Phase 3 — Agents
The six agents, implemented in dependency order — SQL agent (schema introspection, safety
validator, executor), RAG agent (embedding and retrieval), router agent (classification),
synthesis agent (answer generation), verification agent (claim checking and logging), and
finally the orchestrator coordinating them. Each agent was given a standalone demonstration
command allowing it to be exercised in isolation.

### Phase 4 — Evaluation
The experimental harness: similarity scoring against a reference answer set, model warm-up
handling, batch experiment runner with CSV and JSONL output, and a concurrent load tester
reporting time-to-first-token and total-response-time statistics.

### Phase 5 — Production Hardening
Automated first-run provisioning (migrations, read-only role creation, staff account,
demonstration data) via a self-configuring container entrypoint. Session-cookie
authentication replacing token storage, staff-only authorisation, rate limiting, the audit
log, input sanitisation, and secure-cookie and CSRF configuration. Shared client modules
were extracted and a uniform exception hierarchy introduced, enabling the
graceful-degradation policy. An HTTPS reverse proxy with internally-issued certificates
was added so that no service is exposed except over TLS.

### 26 July 2026 — Review and Registration Preparation
Production-readiness review. The read-only role provisioning script was rewritten to accept
its password as a parameter rather than containing a literal credential. Documentation
corrections and a non-technical operator runbook. Proprietary licence, per-file copyright
notices, this statement of work, and the source code submission bundle.

---

## 4. Authorship Statement `[CONFIRM]`

*The following must be completed and verified by the applicant before submission. Do not
file this section as written.*

- **Author:** Yash Garad
- **Nature of authorship:** Design, architecture, and implementation of the complete
  software system described above.
- **Sole or joint authorship:** `[CONFIRM — state whether any other person contributed
  copyrightable expression]`
- **Work made for hire / institutional claim:** `[CONFIRM — if this was produced as
  academic coursework or under an institutional arrangement, your institution may hold
  or share rights. Verify against your institution's intellectual property policy before
  filing, and obtain a No Objection Certificate if one is required.]`
- **Development tooling:** `[CONFIRM — disclose the extent to which AI coding assistants
  were used in producing this code, and confirm how that bears on your authorship claim.
  See the note below.]`
- **Previously published:** `[CONFIRM — yes/no, and date and place of first publication
  if yes]`

### Note on AI-assisted development

Indian copyright law requires a human author. The Copyright Office has, in practice,
raised questions about applications covering material generated with AI assistance, and
the position on AI-generated versus AI-assisted work is unsettled. If AI coding tools were
used in producing this codebase, that does not by itself defeat a copyright claim — but
the extent of human creative contribution to the selection, arrangement, architecture, and
expression is what the claim rests on, and it may need to be stated. This is a question to
put to a copyright practitioner rather than resolve from this document.

---

## 5. Submission Bundle

The materials prepared for filing are in `copyright_submission/`:

| File | Contents |
| --- | --- |
| `SOURCE_CODE_LISTING.md` | Complete source code, organised by folder, with contents page |
| `SOURCE_CODE_LISTING.html` | The same listing, formatted for printing to PDF |
| `college-assistant-source-2026.zip` | The complete source tree as files |
| `MANIFEST.txt` | Every file in the bundle with size, line count, and SHA-256 hash |

No credential file (`.env`), dependency directory, build artefact, or generated data file
is included in the bundle. See `MANIFEST.txt` for the exact inventory.
