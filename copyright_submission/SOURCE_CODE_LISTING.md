# College Assistant - A Multi-Agent Retrieval-Augmented Question Answering System

## Complete Source Code Listing

**Copyright (c) 2026 Yash Garad. All rights reserved.**

| | |
| --- | --- |
| Author / Copyright Owner | Yash Garad |
| Year | 2026 |
| Listing generated | 26 July 2026 |
| Total files | 133 |
| Total lines | 6,439 |

This document contains the complete source code of the work, organised by folder.
Credential files, third-party dependency directories, build artefacts and generated
data files are excluded; see `MANIFEST.txt` for the exact inventory and per-file
SHA-256 hashes.

---

## Contents

**Project Root - Deployment, Licence and Documentation**

1. [`.env.example`](#file--env-example)
2. [`.gitignore`](#file--gitignore)
3. [`CHANGELOG.md`](#file-changelog-md)
4. [`Caddyfile`](#file-caddyfile)
5. [`LICENSE`](#file-license)
6. [`README.md`](#file-readme-md)
7. [`RUNBOOK.md`](#file-runbook-md)
8. [`docker-compose.yml`](#file-docker-compose-yml)

**Database - Read-Only Role Definition**

9. [`db/sql/create_rag_agent_ro.sql`](#file-db-sql-create-rag-agent-ro-sql)

**Backend - Django Application**

10. [`backend/Dockerfile`](#file-backend-dockerfile)
11. [`backend/academics/__init__.py`](#file-backend-academics---init---py)
12. [`backend/academics/apps.py`](#file-backend-academics-apps-py)
13. [`backend/academics/management/commands/seed_demo_data.py`](#file-backend-academics-management-commands-seed-demo-data-py)
14. [`backend/academics/management/commands/setup_readonly_role.py`](#file-backend-academics-management-commands-setup-readonly-role-py)
15. [`backend/academics/migrations/0001_initial.py`](#file-backend-academics-migrations-0001-initial-py)
16. [`backend/academics/migrations/__init__.py`](#file-backend-academics-migrations---init---py)
17. [`backend/academics/models.py`](#file-backend-academics-models-py)
18. [`backend/accounts/__init__.py`](#file-backend-accounts---init---py)
19. [`backend/accounts/apps.py`](#file-backend-accounts-apps-py)
20. [`backend/accounts/management/__init__.py`](#file-backend-accounts-management---init---py)
21. [`backend/accounts/management/commands/__init__.py`](#file-backend-accounts-management-commands---init---py)
22. [`backend/accounts/management/commands/create_staff_user.py`](#file-backend-accounts-management-commands-create-staff-user-py)
23. [`backend/accounts/permissions.py`](#file-backend-accounts-permissions-py)
24. [`backend/accounts/throttling.py`](#file-backend-accounts-throttling-py)
25. [`backend/accounts/urls.py`](#file-backend-accounts-urls-py)
26. [`backend/accounts/views.py`](#file-backend-accounts-views-py)
27. [`backend/audit/__init__.py`](#file-backend-audit---init---py)
28. [`backend/audit/apps.py`](#file-backend-audit-apps-py)
29. [`backend/audit/migrations/0001_initial.py`](#file-backend-audit-migrations-0001-initial-py)
30. [`backend/audit/migrations/__init__.py`](#file-backend-audit-migrations---init---py)
31. [`backend/audit/models.py`](#file-backend-audit-models-py)
32. [`backend/common/__init__.py`](#file-backend-common---init---py)
33. [`backend/common/exceptions.py`](#file-backend-common-exceptions-py)
34. [`backend/common/ollama.py`](#file-backend-common-ollama-py)
35. [`backend/config/__init__.py`](#file-backend-config---init---py)
36. [`backend/config/asgi.py`](#file-backend-config-asgi-py)
37. [`backend/config/settings.py`](#file-backend-config-settings-py)
38. [`backend/config/urls.py`](#file-backend-config-urls-py)
39. [`backend/config/wsgi.py`](#file-backend-config-wsgi-py)
40. [`backend/entrypoint.sh`](#file-backend-entrypoint-sh)
41. [`backend/experiments/__init__.py`](#file-backend-experiments---init---py)
42. [`backend/experiments/apps.py`](#file-backend-experiments-apps-py)
43. [`backend/experiments/fixtures/sample_qa.json`](#file-backend-experiments-fixtures-sample-qa-json)
44. [`backend/experiments/management/__init__.py`](#file-backend-experiments-management---init---py)
45. [`backend/experiments/management/commands/__init__.py`](#file-backend-experiments-management-commands---init---py)
46. [`backend/experiments/management/commands/load_test.py`](#file-backend-experiments-management-commands-load-test-py)
47. [`backend/experiments/management/commands/run_experiment.py`](#file-backend-experiments-management-commands-run-experiment-py)
48. [`backend/experiments/runner.py`](#file-backend-experiments-runner-py)
49. [`backend/experiments/similarity.py`](#file-backend-experiments-similarity-py)
50. [`backend/experiments/warmup.py`](#file-backend-experiments-warmup-py)
51. [`backend/health/__init__.py`](#file-backend-health---init---py)
52. [`backend/health/apps.py`](#file-backend-health-apps-py)
53. [`backend/health/management/__init__.py`](#file-backend-health-management---init---py)
54. [`backend/health/management/commands/__init__.py`](#file-backend-health-management-commands---init---py)
55. [`backend/health/management/commands/check_rag_agent_ro.py`](#file-backend-health-management-commands-check-rag-agent-ro-py)
56. [`backend/health/urls.py`](#file-backend-health-urls-py)
57. [`backend/health/views.py`](#file-backend-health-views-py)
58. [`backend/manage.py`](#file-backend-manage-py)
59. [`backend/orchestrator/__init__.py`](#file-backend-orchestrator---init---py)
60. [`backend/orchestrator/apps.py`](#file-backend-orchestrator-apps-py)
61. [`backend/orchestrator/sanitize.py`](#file-backend-orchestrator-sanitize-py)
62. [`backend/orchestrator/service.py`](#file-backend-orchestrator-service-py)
63. [`backend/orchestrator/urls.py`](#file-backend-orchestrator-urls-py)
64. [`backend/orchestrator/views.py`](#file-backend-orchestrator-views-py)
65. [`backend/rag_agent/__init__.py`](#file-backend-rag-agent---init---py)
66. [`backend/rag_agent/apps.py`](#file-backend-rag-agent-apps-py)
67. [`backend/rag_agent/embedder.py`](#file-backend-rag-agent-embedder-py)
68. [`backend/rag_agent/management/__init__.py`](#file-backend-rag-agent-management---init---py)
69. [`backend/rag_agent/management/commands/__init__.py`](#file-backend-rag-agent-management-commands---init---py)
70. [`backend/rag_agent/management/commands/demo_rag_agent.py`](#file-backend-rag-agent-management-commands-demo-rag-agent-py)
71. [`backend/rag_agent/service.py`](#file-backend-rag-agent-service-py)
72. [`backend/rag_agent/vector_store.py`](#file-backend-rag-agent-vector-store-py)
73. [`backend/requirements.txt`](#file-backend-requirements-txt)
74. [`backend/router_agent/__init__.py`](#file-backend-router-agent---init---py)
75. [`backend/router_agent/apps.py`](#file-backend-router-agent-apps-py)
76. [`backend/router_agent/classifier.py`](#file-backend-router-agent-classifier-py)
77. [`backend/router_agent/llm_client.py`](#file-backend-router-agent-llm-client-py)
78. [`backend/router_agent/management/__init__.py`](#file-backend-router-agent-management---init---py)
79. [`backend/router_agent/management/commands/__init__.py`](#file-backend-router-agent-management-commands---init---py)
80. [`backend/router_agent/management/commands/demo_router_agent.py`](#file-backend-router-agent-management-commands-demo-router-agent-py)
81. [`backend/sql_agent/__init__.py`](#file-backend-sql-agent---init---py)
82. [`backend/sql_agent/apps.py`](#file-backend-sql-agent-apps-py)
83. [`backend/sql_agent/db.py`](#file-backend-sql-agent-db-py)
84. [`backend/sql_agent/executor.py`](#file-backend-sql-agent-executor-py)
85. [`backend/sql_agent/guard.py`](#file-backend-sql-agent-guard-py)
86. [`backend/sql_agent/llm_client.py`](#file-backend-sql-agent-llm-client-py)
87. [`backend/sql_agent/management/__init__.py`](#file-backend-sql-agent-management---init---py)
88. [`backend/sql_agent/management/commands/__init__.py`](#file-backend-sql-agent-management-commands---init---py)
89. [`backend/sql_agent/management/commands/demo_sql_agent.py`](#file-backend-sql-agent-management-commands-demo-sql-agent-py)
90. [`backend/sql_agent/schema.py`](#file-backend-sql-agent-schema-py)
91. [`backend/sql_agent/service.py`](#file-backend-sql-agent-service-py)
92. [`backend/sql_agent/tests.py`](#file-backend-sql-agent-tests-py)
93. [`backend/synthesis_agent/__init__.py`](#file-backend-synthesis-agent---init---py)
94. [`backend/synthesis_agent/apps.py`](#file-backend-synthesis-agent-apps-py)
95. [`backend/synthesis_agent/llm_client.py`](#file-backend-synthesis-agent-llm-client-py)
96. [`backend/synthesis_agent/management/__init__.py`](#file-backend-synthesis-agent-management---init---py)
97. [`backend/synthesis_agent/management/commands/__init__.py`](#file-backend-synthesis-agent-management-commands---init---py)
98. [`backend/synthesis_agent/management/commands/demo_synthesis_agent.py`](#file-backend-synthesis-agent-management-commands-demo-synthesis-agent-py)
99. [`backend/synthesis_agent/service.py`](#file-backend-synthesis-agent-service-py)
100. [`backend/verification_agent/__init__.py`](#file-backend-verification-agent---init---py)
101. [`backend/verification_agent/apps.py`](#file-backend-verification-agent-apps-py)
102. [`backend/verification_agent/llm_client.py`](#file-backend-verification-agent-llm-client-py)
103. [`backend/verification_agent/management/__init__.py`](#file-backend-verification-agent-management---init---py)
104. [`backend/verification_agent/management/commands/__init__.py`](#file-backend-verification-agent-management-commands---init---py)
105. [`backend/verification_agent/management/commands/demo_verification_agent.py`](#file-backend-verification-agent-management-commands-demo-verification-agent-py)
106. [`backend/verification_agent/migrations/0001_initial.py`](#file-backend-verification-agent-migrations-0001-initial-py)
107. [`backend/verification_agent/migrations/__init__.py`](#file-backend-verification-agent-migrations---init---py)
108. [`backend/verification_agent/models.py`](#file-backend-verification-agent-models-py)
109. [`backend/verification_agent/service.py`](#file-backend-verification-agent-service-py)

**Sync Worker - Incremental Embedding Pipeline**

110. [`sync_worker/Dockerfile`](#file-sync-worker-dockerfile)
111. [`sync_worker/chunker.py`](#file-sync-worker-chunker-py)
112. [`sync_worker/config.py`](#file-sync-worker-config-py)
113. [`sync_worker/embedder.py`](#file-sync-worker-embedder-py)
114. [`sync_worker/lookups.py`](#file-sync-worker-lookups-py)
115. [`sync_worker/main.py`](#file-sync-worker-main-py)
116. [`sync_worker/poller.py`](#file-sync-worker-poller-py)
117. [`sync_worker/queue_writer.py`](#file-sync-worker-queue-writer-py)
118. [`sync_worker/requirements.txt`](#file-sync-worker-requirements-txt)
119. [`sync_worker/state.py`](#file-sync-worker-state-py)
120. [`sync_worker/test_embedding_pipeline.py`](#file-sync-worker-test-embedding-pipeline-py)
121. [`sync_worker/vector_store.py`](#file-sync-worker-vector-store-py)

**Frontend - React Client**

122. [`frontend/Dockerfile`](#file-frontend-dockerfile)
123. [`frontend/index.html`](#file-frontend-index-html)
124. [`frontend/package.json`](#file-frontend-package-json)
125. [`frontend/postcss.config.js`](#file-frontend-postcss-config-js)
126. [`frontend/src/App.jsx`](#file-frontend-src-app-jsx)
127. [`frontend/src/api.js`](#file-frontend-src-api-js)
128. [`frontend/src/components/Chat.jsx`](#file-frontend-src-components-chat-jsx)
129. [`frontend/src/components/Login.jsx`](#file-frontend-src-components-login-jsx)
130. [`frontend/src/index.css`](#file-frontend-src-index-css)
131. [`frontend/src/main.jsx`](#file-frontend-src-main-jsx)
132. [`frontend/tailwind.config.js`](#file-frontend-tailwind-config-js)
133. [`frontend/vite.config.js`](#file-frontend-vite-config-js)

---

# Project Root - Deployment, Licence and Documentation

## 1. `.env.example`

*62 lines*

```text
# Copyright (c) 2026 Yash Garad. All rights reserved.

# Copy to .env and adjust as needed.

# Postgres
POSTGRES_DB=college_rag
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_HOST=postgres
POSTGRES_PORT=5432

# Django
DJANGO_SECRET_KEY=dev-insecure-secret-key-change-me
DJANGO_DEBUG=true
DJANGO_ALLOWED_HOSTS=*

# The hostname or IP the server is reached at over HTTPS. Set this to your
# server's LAN IP (e.g. 192.168.1.50) so CSRF/HTTPS trust it. 'localhost' is
# fine when testing on the server itself.
SERVER_HOST=localhost
# Cookies are marked Secure (HTTPS-only) by default. Only set false if you
# deliberately run without the HTTPS proxy.
COOKIE_SECURE=true

# Staff login created automatically on first startup (change these for real use)
STAFF_USERNAME=staff
STAFF_PASSWORD=staffpass123

# Set to false to skip loading the built-in demo dataset on first startup
SEED_DEMO_DATA=true

# Qdrant
QDRANT_URL=http://qdrant:6333
QDRANT_COLLECTION=college_docs

# Ollama
OLLAMA_BASE_URL=http://ollama:11434
EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_DIM=768

# The language model all four agents use, and the one the stack downloads on
# first start. This is the single place to change the model.
#   qwen2.5:7b  (default) ~4.7 GB — best answer quality
#   qwen2.5:3b            ~1.9 GB — smaller/faster, lower quality (good on modest hardware)
#   qwen2.5:1.5b         ~1 GB   — smallest/fastest, noticeably weaker
# After changing this, run: docker compose up -d   (it will download the new model)
LLM_MODEL=qwen2.5:7b
# Optional: override the model for a single agent (defaults to LLM_MODEL if unset)
# SQL_AGENT_MODEL=qwen2.5:7b
# ROUTER_MODEL=qwen2.5:7b
# SYNTHESIS_MODEL=qwen2.5:7b
# VERIFICATION_MODEL=qwen2.5:7b

# sync_worker
SYNC_WORKER_POLL_INTERVAL_SECONDS=30

# rag_agent_ro (read-only DB role, see db/sql/create_rag_agent_ro.sql)
RAG_AGENT_RO_HOST=postgres
RAG_AGENT_RO_PORT=5432
RAG_AGENT_RO_DB=college_rag
RAG_AGENT_RO_USER=rag_agent_ro
RAG_AGENT_RO_PASSWORD=CHANGE_ME_STRONG_PASSWORD
```

## 2. `.gitignore`

*29 lines*

```text
# Copyright (c) 2026 Yash Garad. All rights reserved.

# env
.env

# python
__pycache__/
*.pyc
venv/
.venv/

# node
node_modules/
dist/

# docker volumes (bind-mounted data, if any)
postgres_data/
qdrant_data/
ollama_data/

# sync_worker runtime state (watermarks + change queue log)
sync_worker/data/

# experiment output (regenerated CSV/JSONL research results)
backend/experiment_results/

# editor
.vscode/
.idea/
```

## 3. `CHANGELOG.md`

*235 lines*

```markdown
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
```

## 4. `Caddyfile`

*28 lines*

```text
# Copyright (c) 2026 Yash Garad. All rights reserved.

# HTTPS reverse proxy for the College Assistant.
#
# The site is named (localhost + whatever SERVER_HOST is set to) so Caddy's
# `tls internal` issuer can mint a certificate for those names from a locally-
# trusted CA — no public domain or internet needed, suited to an internal LAN.
# The browser talks only to Caddy (443); Caddy forwards /api/* to the Django
# backend and everything else to the frontend, so the SPA and API share one
# HTTPS origin (no CORS, and session cookies get the Secure flag). Caddy also
# auto-redirects plain HTTP (80) to HTTPS.

localhost, {$SERVER_HOST:localhost} {
	tls internal
	encode gzip

	# API -> Django. SSE streaming is passed through unbuffered.
	handle /api/* {
		reverse_proxy backend:8000 {
			flush_interval -1
		}
	}

	# Everything else -> the frontend (Vite) dev server.
	handle {
		reverse_proxy frontend:5173
	}
}
```

## 5. `LICENSE`

*125 lines*

```text
PROPRIETARY SOFTWARE LICENSE
All Rights Reserved

College Assistant — A Multi-Agent Retrieval-Augmented Question Answering System
Copyright (c) 2026 Yash Garad. All rights reserved.

------------------------------------------------------------------------------
1. OWNERSHIP
------------------------------------------------------------------------------

This software, including all source code, object code, configuration files,
database schemas, prompt designs, documentation, and any accompanying materials
(collectively, the "Software"), is the exclusive property of Yash Garad (the
"Owner") and is protected by the Copyright Act, 1957 (India), as amended, and
by applicable international copyright treaties and conventions.

The Software is licensed, not sold. No transfer of ownership, title, or
intellectual property rights of any kind is made or implied by the possession,
receipt, or use of a copy of the Software.

------------------------------------------------------------------------------
2. NO LICENSE GRANTED
------------------------------------------------------------------------------

No rights or licenses are granted under this document, whether by implication,
estoppel, or otherwise, except as expressly stated in a separate written
agreement signed by the Owner.

Without the prior express written permission of the Owner, no person or entity
may:

  (a) copy, reproduce, or duplicate the Software, in whole or in part;
  (b) modify, adapt, translate, or create derivative works from the Software;
  (c) distribute, publish, sublicense, sell, rent, lease, lend, or otherwise
      transfer the Software or any copy thereof to any third party;
  (d) host, deploy, or make the Software available as a service to any third
      party, whether or not for a fee;
  (e) reverse engineer, decompile, or disassemble the Software, except to the
      limited extent such restriction is expressly prohibited by applicable law;
  (f) remove, obscure, or alter any copyright notice, proprietary legend, or
      attribution contained in or on the Software; or
  (g) use the Software for any commercial purpose.

------------------------------------------------------------------------------
3. AUTHORIZED USE
------------------------------------------------------------------------------

Any permitted use of the Software is governed solely by the terms of a separate
written licence agreement executed by the Owner. In the absence of such an
agreement, no use is authorized.

------------------------------------------------------------------------------
4. THIRD-PARTY COMPONENTS
------------------------------------------------------------------------------

The Software is designed to operate together with third-party software
components that are NOT owned by the Owner and are NOT covered by this licence.
Each such component remains subject to its own licence terms, and nothing in
this document modifies, supersedes, or restricts those terms.

These components are obtained at build time via the declared dependency
manifests and are not distributed as part of the Software. They include,
without limitation:

  Backend (see backend/requirements.txt)
    Django, Django REST Framework, django-cors-headers, psycopg2-binary,
    python-dotenv, gunicorn, sqlglot, qdrant-client, requests

  Frontend (see frontend/package.json)
    React, React DOM, Vite, @vitejs/plugin-react, Tailwind CSS, PostCSS,
    Autoprefixer

  Container images (see docker-compose.yml)
    PostgreSQL, Qdrant, Ollama, Caddy, and the language models served by
    Ollama

The Owner's claim of copyright extends only to the original work of authorship
in the Software — the application source code, architecture, agent designs,
prompt engineering, security controls, and documentation authored by the Owner —
and does not extend to any third-party component listed above.

------------------------------------------------------------------------------
5. DISCLAIMER OF WARRANTY
------------------------------------------------------------------------------

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE, ACCURACY, AND NON-INFRINGEMENT.

The Software incorporates automated language-model-generated output. Such output
may be incomplete, inaccurate, or otherwise unsuitable for any particular
purpose, and must not be relied upon as authoritative without independent
verification.

------------------------------------------------------------------------------
6. LIMITATION OF LIABILITY
------------------------------------------------------------------------------

IN NO EVENT SHALL THE OWNER BE LIABLE FOR ANY CLAIM, DAMAGES, OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT, OR OTHERWISE, ARISING FROM,
OUT OF, OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

------------------------------------------------------------------------------
7. GOVERNING LAW
------------------------------------------------------------------------------

This licence shall be governed by and construed in accordance with the laws of
India, without regard to its conflict-of-law provisions. The courts of India
shall have exclusive jurisdiction over any dispute arising out of or in
connection with this licence.

------------------------------------------------------------------------------
8. CONTACT
------------------------------------------------------------------------------

For licensing enquiries, permissions, or any other matter relating to this
Software, contact the Owner:

    Yash Garad
    agamemnon1527@gmail.com

------------------------------------------------------------------------------

END OF TERMS
```

## 6. `README.md`

*248 lines*

```markdown
# College Assistant

An offline AI assistant that answers questions about a college's database — courses,
departments, faculty, fees, schedules, and more — through a simple chat website. Everything
runs on your own server; no data leaves the machine.

This guide is written for someone with **no coding background**. If you can install a program
and copy-paste a few lines into a terminal, you can run this.

> **Already installed?** For everyday running — starting, health checks, logs, and
> troubleshooting — use the one-page [RUNBOOK.md](RUNBOOK.md) instead of this file.

---

## What you need first

1. **A server or computer** running Windows, macOS, or Linux, with at least:
   - **16 GB of RAM** (the AI model is large)
   - **20 GB of free disk space**
2. **Docker Desktop** — the one program that runs everything else.
   - Download it here: https://www.docker.com/products/docker-desktop/
   - Install it, then **start it** and wait until its whale icon says "Docker Desktop is running."

That's the only software you install by hand. Everything else is handled automatically.

---

## Setup — step by step

### 1. Get the project files onto the server
Copy the whole project folder (the one containing this README and the file named
`docker-compose.yml`) onto the machine. Remember where you put it.

### 2. Open a terminal in that folder
- **Windows:** open the folder in File Explorer, click the address bar, type `powershell`, and press Enter.
- **macOS:** right-click the folder → "New Terminal at Folder."
- **Linux:** open a terminal and `cd` into the folder.

### 3. Create the settings file
The project comes with an example settings file. Make your own copy of it by running:

- **Windows (PowerShell):**
  ```
  copy .env.example .env
  ```
- **macOS / Linux:**
  ```
  cp .env.example .env
  ```

You can use the file as-is to try things out. **For real use, open `.env` in a text editor
and change every password** (see "Security" below).

### 4. Start everything with one command
```
docker compose up -d
```
That's it. This single command builds and starts all six parts of the system.

### 5. Wait for the first startup to finish
**The very first time only,** the system downloads the AI models — about **5 GB**, which can
take **10–20 minutes** depending on your internet speed. You only wait this once; future
startups take seconds.

To watch the download progress:
```
docker compose logs -f ollama-pull
```
When you see **`All AI models are ready.`**, press `Ctrl + C` to stop watching. The assistant
is now ready.

### 6. Open the website
The assistant is served over **HTTPS**. In a web browser, go to:
```
https://localhost
```
(or `https://<your-server-ip>` from another machine on the network — see "Access from other
computers" below).

**You will see a "your connection is not private" warning.** This is expected: the server uses
a self-signed certificate (fine for an internal network — no public certificate authority is
involved). Click **Advanced → Proceed** to continue. To remove the warning, install the server's
local certificate authority on each computer (see "Trusting the certificate" below).

Log in with the staff account:
- **Username:** `staff`
- **Password:** `staffpass123`

(These come from your `.env` file — change them for real use.)

Ask a question like *"What courses does the Computer Science department offer?"* and the answer
streams back word by word.

### Access from other computers on the network
1. Find the server's IP address (e.g. `192.168.1.50`).
2. On the server, set `SERVER_HOST=192.168.1.50` in `.env`, then run `docker compose up -d`.
3. On any other computer, open `https://192.168.1.50` and accept the certificate warning.

### Trusting the certificate (optional, removes the browser warning)
The server's local certificate authority file is created by Caddy. To copy it out of the
running system:
```
docker compose cp caddy:/data/caddy/pki/authorities/local/root.crt ./college-assistant-ca.crt
```
Install `college-assistant-ca.crt` as a trusted root certificate authority on each computer
(Windows: double-click → "Install Certificate" → "Local Machine" → "Trusted Root Certification
Authorities"). After that, the browser warning disappears.

---

## Everyday commands

Run these from a terminal in the project folder.

| What you want to do | Command |
| --- | --- |
| Start the system | `docker compose up -d` |
| Stop the system | `docker compose down` |
| Restart the system | `docker compose restart` |
| See if everything is running | `docker compose ps` |
| Watch what the system is doing | `docker compose logs -f` |
| Check the AI model download | `docker compose logs -f ollama-pull` |

Stopping the system with `docker compose down` **keeps all your data** (it is saved in Docker
"volumes"). Your questions, the database, and the downloaded models are all still there next
time you start it.

---

## Is it working? Quick checks

- **Website loads:** open https://localhost — you should see a login screen (accept the
  self-signed certificate warning).
- **Backend is healthy:** open https://localhost/api/health/ — you should see
  `{"status": "ok", "services": {"database": "up", "llm": "up", "vector_store": "up"}}`.
  If it says `"degraded"`, whichever service reads `"down"` is the broken one.
- **Everything is "Up":** run `docker compose ps` and check each row says `running` or `healthy`.

---

## What's inside (plain-language overview)

The one command starts six cooperating pieces:

| Piece | What it does |
| --- | --- |
| **frontend** | The chat website you open in a browser. |
| **backend** | The brain that receives questions and produces answers. |
| **ollama** | Runs the AI language model locally (no internet needed after setup). |
| **qdrant** | A search index that helps find relevant information quickly. |
| **postgres** | The database that stores the college's information. |
| **sync worker** | Keeps the search index up to date as the database changes. |

On first startup the backend automatically sets up the database, creates a locked-down
read-only account for the AI, creates your staff login, and loads a small demo dataset so you
have something to try immediately.

---

## Security (please read before real use)

The default passwords in `.env` are for **testing only**. Before using this with real data,
open the `.env` file in a text editor and change:

- `POSTGRES_PASSWORD` — the main database password
- `RAG_AGENT_RO_PASSWORD` — the AI's read-only database password
- `DJANGO_SECRET_KEY` — a long random string (any 50+ random characters)
- `STAFF_PASSWORD` — the password you log in with

After changing `.env`, apply it with:
```
docker compose up -d
```

For a server that is reachable from the internet, also set `DJANGO_DEBUG=false` and put the
server behind HTTPS. Ask a technical colleague to help with that part.

---

## Choosing the AI model (smaller = faster download and replies)

The assistant's answer quality, speed, and first-run download size all come from one model.
If your server has modest hardware or you want a quicker first startup, you can switch to a
smaller model by editing one line in `.env`:

```
LLM_MODEL=qwen2.5:7b
```

| Value | Download | Notes |
| --- | --- | --- |
| `qwen2.5:7b` | ~4.7 GB | Default. Best answer quality. |
| `qwen2.5:3b` | ~1.9 GB | Smaller and faster; slightly lower quality. Good for modest servers. |
| `qwen2.5:1.5b` | ~1 GB | Smallest and fastest; noticeably weaker answers. |

After changing the value, apply it with:
```
docker compose up -d
```
The system will download the new model (a one-time wait) and use it everywhere automatically.

## Turning off the demo data

By default the system loads a small set of example courses on first startup so you can try it
right away. To start empty instead (for loading your own real data), set this in `.env` before
the first run:
```
SEED_DEMO_DATA=false
```

---

## Troubleshooting

**"docker: command not found" or nothing happens**
Docker Desktop isn't installed or isn't running. Open Docker Desktop and wait for it to say
it's running, then try again.

**The website won't load / says it can't connect**
The AI models may still be downloading on first startup. Check with
`docker compose logs -f ollama-pull` and wait for `All AI models are ready.`

**A question returns an error**
If it's the first startup, the models may not be ready yet — wait for the download to finish.
Otherwise, check the logs with `docker compose logs -f backend`.

**I want to start completely fresh (erase everything)**
This deletes all data, the database, and the downloaded models:
```
docker compose down -v
```
The next `docker compose up -d` will set everything up again from scratch (including the long
model download).

---

## Getting help

If something isn't working, capture what the system reports and share it with your technical
contact:
```
docker compose ps
docker compose logs --tail 100
```

---

*Copyright (c) 2026 Yash Garad. All rights reserved.*
```

## 7. `RUNBOOK.md`

*147 lines*

```markdown
# Day-to-Day Runbook

A one-page card for whoever looks after the College Assistant. **No coding knowledge needed.**
For first-time installation, see [README.md](README.md) instead — this page assumes it's already set up.

Everything below is typed into a terminal **opened in the project folder** (the folder containing
the file `docker-compose.yml`).

- **Windows:** open the folder in File Explorer, click the address bar, type `powershell`, press Enter.
- **macOS:** right-click the folder → "New Terminal at Folder."
- **Linux:** open a terminal, `cd` into the folder.

---

## Starting and stopping

| What you want | Type this |
| --- | --- |
| Start the system | `docker compose up -d` |
| Stop the system | `docker compose down` |
| Restart everything | `docker compose restart` |

Before any of these, make sure **Docker Desktop is open and running** (its whale icon should say
"Docker Desktop is running"). Nothing works until it is.

Starting takes about a minute. **The very first start ever** also downloads ~5 GB of AI models and
can take 10–20 minutes — that happens once, not every time.

`docker compose down` does **not** delete anything. Your database, your questions, and the
downloaded models all survive a stop, a restart, and a reboot of the server.

---

## Is it healthy?

Three checks, quickest first. If all three pass, the system is fine.

**1. Are all the pieces running?**
```
docker compose ps
```
You should see a row for each piece with `running` or `healthy` in the STATUS column.
`ollama-pull` showing `exited (0)` is **correct** — that one is a helper that finishes its job
and stops on purpose. Anything else saying `exited`, `restarting`, or `unhealthy` is a problem.

**2. Is the brain answering?**
Open this in a browser: `https://localhost/api/health/`

- `{"status": "ok", ...}` → everything is up.
- `{"status": "degraded", "services": {...}}` → read the list; whichever says `"down"` is the
  broken piece. Note that name — you'll need it below.

**3. Can you actually use it?**
Open `https://localhost`, log in, and ask a question like *"What courses does the Computer Science
department offer?"* If words stream back, it's genuinely working.

> The browser will warn "your connection is not private." That is expected on an internal
> network — click **Advanced → Proceed**. See the README for how to remove the warning.

---

## Viewing logs

Logs are the system telling you what it's doing. Read them whenever something looks wrong.

| What you want to see | Type this |
| --- | --- |
| Everything, live | `docker compose logs -f` |
| Just one piece, live | `docker compose logs -f backend` |
| The last 100 lines | `docker compose logs --tail 100` |
| First-run model download | `docker compose logs -f ollama-pull` |

Press **`Ctrl + C`** to stop watching. That stops the *watching*, not the system.

Replace `backend` with whichever piece you care about: `backend`, `frontend`, `postgres`,
`qdrant`, `ollama`, `sync_worker`, `caddy`.

**What you're looking for:** lines containing `ERROR`, `Traceback`, or `refused`. The last
20–30 lines before a failure are usually the useful part.

---

## Troubleshooting

Work down the list — the fixes get more drastic, so try them in order.

**The website won't open at all**
1. Is Docker Desktop running? Open it and wait for "Docker Desktop is running."
2. Run `docker compose ps`. If nothing is listed, run `docker compose up -d`.
3. If this is the first start ever, the AI models are still downloading. Watch
   `docker compose logs -f ollama-pull` and wait for `All AI models are ready.`

**The browser says "your connection is not private"**
Expected and safe on your own network. Click **Advanced → Proceed**. To stop it happening on
every machine, install the certificate — README, "Trusting the certificate."

**I can't log in**
The username and password come from the `STAFF_USERNAME` / `STAFF_PASSWORD` lines in the `.env`
file in the project folder. Open it in a text editor to check them. If you change them, run
`docker compose up -d` afterwards to apply.

**Questions return an error, or the answer never appears**
1. Check `https://localhost/api/health/` and see which service says `"down"`.
2. Restart just that piece — e.g. if `llm` is down: `docker compose restart ollama`.
3. Wait 30 seconds, then check health again.
4. Still broken? `docker compose logs --tail 100 backend` and read the last error.

**Answers are very slow**
Normal on modest hardware — the AI runs entirely on your own server. If it's unusable, switch to
a smaller model: open `.env`, change `LLM_MODEL=qwen2.5:7b` to `LLM_MODEL=qwen2.5:3b`, then run
`docker compose up -d`. See README, "Choosing the AI model."

**The assistant doesn't know about data we just added**
The search index updates on a timer (about every 30 seconds). Wait a minute, then ask again. If
it's still missing, check `docker compose logs --tail 50 sync_worker` for errors.

**Something is deeply stuck — reset without losing data**
```
docker compose down
docker compose up -d
```

**Last resort — erase everything and start over**
```
docker compose down -v
docker compose up -d
```
> ⚠️ The `-v` **permanently deletes the database, all question history, and the downloaded
> models.** Only do this if you have a backup or the data doesn't matter. The next start will
> redo the full 5 GB download.

---

## When you need to ask for help

Copy the output of both of these and send it to your technical contact:

```
docker compose ps
docker compose logs --tail 100
```

Also say: what you did, what you expected, and what happened instead.

---

*Copyright (c) 2026 Yash Garad. All rights reserved.*
```

## 8. `docker-compose.yml`

*202 lines*

```yaml
# Copyright (c) 2026 Yash Garad. All rights reserved.

services:
  postgres:
    image: postgres:16-alpine
    restart: always
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-college_rag}
      POSTGRES_USER: ${POSTGRES_USER:-postgres}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-postgres}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      # Bound to localhost only — internal services are never exposed on the
      # LAN. External access is exclusively through the Caddy HTTPS proxy.
      - "127.0.0.1:5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-postgres}"]
      interval: 5s
      timeout: 5s
      retries: 10
    networks:
      - college_rag_net

  qdrant:
    image: qdrant/qdrant:latest
    restart: always
    volumes:
      - qdrant_data:/qdrant/storage
    ports:
      - "127.0.0.1:6333:6333"
      - "127.0.0.1:6334:6334"
    networks:
      - college_rag_net

  ollama:
    image: ollama/ollama:latest
    restart: always
    volumes:
      - ollama_data:/root/.ollama
    # No host port published: Ollama is internal-only, reached by the backend
    # and sync_worker over the docker network at http://ollama:11434. (Not
    # publishing it also avoids colliding with a desktop Ollama app on the host.)
    healthcheck:
      test: ["CMD", "ollama", "list"]
      interval: 10s
      timeout: 5s
      retries: 10
    networks:
      - college_rag_net

  # One-shot helper: downloads the AI models into the shared ollama volume the
  # first time the stack starts, so nobody has to run `ollama pull` by hand.
  # On later starts the models are already cached, so this finishes instantly.
  # It exits when done (not a long-running service), hence restart: "no".
  #
  # The download is ~5 GB on first run, so a transient network hiccup mid-pull
  # is a real risk. The loop below retries each model up to 5 times (ollama
  # resumes from cached layers, so a retry doesn't re-download what already
  # landed) and only gives up — loudly — after that. Models are read from the
  # same env vars the app uses, so switching models is a one-place change.
  ollama-pull:
    image: ollama/ollama:latest
    depends_on:
      ollama:
        condition: service_healthy
    environment:
      OLLAMA_HOST: http://ollama:11434
      EMBEDDING_MODEL: ${EMBEDDING_MODEL:-nomic-embed-text}
      LLM_MODEL: ${LLM_MODEL:-qwen2.5:7b}
    entrypoint: ["/bin/sh", "-c"]
    command:
      - |
        for model in "$$EMBEDDING_MODEL" "$$LLM_MODEL"; do
          echo "Downloading $$model (first run can take several minutes)..."
          n=0
          until ollama pull "$$model"; do
            n=$$((n + 1))
            if [ "$$n" -ge 5 ]; then
              echo "ERROR: could not download $$model after 5 attempts. Check the server's internet connection, then run 'docker compose up -d' again."
              exit 1
            fi
            echo "Download of $$model failed (attempt $$n/5) — retrying in 15s..."
            sleep 15
          done
        done
        echo "All AI models are ready."
    restart: "no"
    networks:
      - college_rag_net

  backend:
    build:
      context: ./backend
    restart: always
    env_file:
      - .env
    environment:
      POSTGRES_HOST: postgres
      QDRANT_URL: http://qdrant:6333
      OLLAMA_BASE_URL: http://ollama:11434
      SERVER_HOST: ${SERVER_HOST:-localhost}
      COOKIE_SECURE: ${COOKIE_SECURE:-true}
    ports:
      - "127.0.0.1:8000:8000"
    depends_on:
      postgres:
        condition: service_healthy
      qdrant:
        condition: service_started
      ollama:
        condition: service_started
    volumes:
      - ./backend:/app
    healthcheck:
      # Liveness only (backend process is serving). Uses /api/health/live/ so a
      # downstream outage (e.g. Ollama) never marks the backend itself
      # unhealthy — the aggregate /api/health/ is for monitoring, not liveness.
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health/live/')"]
      interval: 10s
      timeout: 5s
      retries: 20
      start_period: 60s
    networks:
      - college_rag_net

  frontend:
    build:
      context: ./frontend
    restart: always
    env_file:
      - .env
    environment:
      VITE_API_PROXY_TARGET: http://backend:8000
    ports:
      - "127.0.0.1:5173:5173"
    depends_on:
      backend:
        condition: service_healthy
    volumes:
      - ./frontend:/app
      - /app/node_modules
    networks:
      - college_rag_net

  sync_worker:
    build:
      context: ./sync_worker
    restart: always
    env_file:
      - .env
    environment:
      POSTGRES_HOST: postgres
      QDRANT_URL: http://qdrant:6333
      OLLAMA_BASE_URL: http://ollama:11434
    depends_on:
      postgres:
        condition: service_healthy
      qdrant:
        condition: service_started
      # Wait for the backend so migrations + the rag_agent_ro role exist before
      # the worker tries to read as that role.
      backend:
        condition: service_healthy
    volumes:
      - ./sync_worker:/app
    networks:
      - college_rag_net

  # The ONLY service exposed on the network. Terminates HTTPS (self-signed via
  # `tls internal`) and reverse-proxies to the backend/frontend. Everything
  # else is bound to 127.0.0.1, so the LAN can only reach the app over TLS.
  caddy:
    image: caddy:2-alpine
    restart: always
    environment:
      SERVER_HOST: ${SERVER_HOST:-localhost}
    depends_on:
      backend:
        condition: service_healthy
      frontend:
        condition: service_started
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
      - caddy_config:/config
    networks:
      - college_rag_net

networks:
  college_rag_net:
    driver: bridge

volumes:
  postgres_data:
  qdrant_data:
  ollama_data:
  caddy_data:
  caddy_config:
```

# Database - Read-Only Role Definition

## 9. `db/sql/create_rag_agent_ro.sql`

*106 lines*

```sql
-- Copyright (c) 2026 Yash Garad. All rights reserved.

-- ============================================================================
-- Read-only Postgres role for the RAG agent.
--
-- WHAT THIS DOES:
--   - Creates (or resets the flags on) a login role `rag_agent_ro` that:
--       * cannot create databases, roles, or replicate
--       * defaults every session to a read-only transaction (defense in depth,
--         on top of the grants below — belt and suspenders)
--       * has USAGE on the `public` schema but no privileges on any table
--         until explicitly granted below
--       * gets SELECT on the whitelisted tables ONLY — nothing else, no
--         wildcard grants, no future-table auto-grants
--
-- YOU DO NOT NORMALLY NEED TO RUN THIS. The backend applies exactly these
-- statements on every startup via `manage.py setup_readonly_role` (see
-- backend/academics/management/commands/setup_readonly_role.py), reading the
-- password from RAG_AGENT_RO_PASSWORD in .env. This file is the reference
-- copy / manual fallback.
--
-- NO PASSWORD IS WRITTEN IN THIS FILE, deliberately — the secret lives only in
-- .env (which is gitignored). The password is passed in as a psql variable.
--
-- HOW TO RUN MANUALLY (from the repo root, with the stack up):
--   docker compose exec -T postgres psql -U postgres -d college_rag \
--     -v pw="$RAG_AGENT_RO_PASSWORD" -f - < db/sql/create_rag_agent_ro.sql
--
-- Never replace :'pw' below with a literal password — that would put a live
-- secret into a file that gets copied, committed, and shared.
-- ============================================================================

\if :{?pw}
\else
    \echo 'ERROR: no password supplied. Re-run with -v pw="$RAG_AGENT_RO_PASSWORD"'
    \quit 1
\endif

-- Create only if missing. Done with psql's \if rather than a DO $$ block
-- because psql does NOT interpolate :'pw' inside dollar-quoted strings — the
-- variable would be sent to the server verbatim and fail.
SELECT NOT EXISTS (
    SELECT FROM pg_catalog.pg_roles WHERE rolname = 'rag_agent_ro'
) AS role_missing \gset

\if :role_missing
CREATE ROLE rag_agent_ro LOGIN PASSWORD :'pw';
\endif

-- Keep the password in sync with .env even if the role already existed.
ALTER ROLE rag_agent_ro LOGIN PASSWORD :'pw';

ALTER ROLE rag_agent_ro
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE
    NOREPLICATION
    CONNECTION LIMIT 10;

-- Session-level default is a separate ALTER ROLE ... SET statement in Postgres
-- (can't be combined with the role-attribute clauses above).
ALTER ROLE rag_agent_ro SET default_transaction_read_only = on;

-- Lock down the schema itself: PUBLIC (i.e. every role, by default) loses
-- the implicit CREATE/USAGE it gets on a fresh database. rag_agent_ro then
-- gets USAGE explicitly, and only USAGE — it can look up objects, not create them.
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT CONNECT ON DATABASE college_rag TO rag_agent_ro;
GRANT USAGE ON SCHEMA public TO rag_agent_ro;

-- Clean slate: strip any privileges this role may already have on every
-- table in the schema, so re-running this script never leaves stale grants
-- around if a table gets removed from the whitelist later.
REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM rag_agent_ro;

-- ----------------------------------------------------------------------------
-- General institutional data ONLY — no per-student records. The agent's job
-- is general Q&A (courses offered, departments, faculty, timetable, fee
-- structure), not lookups tied to an individual student's identity.
--
-- Deliberately EXCLUDED (per-student / sensitive — see backend/academics/models.py):
--   students, enrollments, attendance, exam_results, fee_payments
-- Also excluded: Django's own auth_*/django_* tables (not college data at all).
-- ----------------------------------------------------------------------------
GRANT SELECT ON
    public.departments,
    public.faculty,
    public.programs,
    public.courses,
    public.courses_prerequisites,
    public.course_offerings,
    public.rooms,
    public.class_schedule,
    public.exam_timetable,
    public.fee_structure
TO rag_agent_ro;

-- No GRANT on sequences, functions, or other schemas — SELECT on the
-- whitelisted tables is the entire privilege surface for this role.

-- Sanity check: list what rag_agent_ro can now see (run separately or as
-- the last statement here; safe to leave in since it's read-only itself).
SELECT grantee, table_schema, table_name, privilege_type
FROM information_schema.role_table_grants
WHERE grantee = 'rag_agent_ro'
ORDER BY table_schema, table_name;
```

# Backend - Django Application

## 10. `backend/Dockerfile`

*24 lines*

```text
# Copyright (c) 2026 Yash Garad. All rights reserved.

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# entrypoint.sh runs migrations, sets up the read-only DB role, creates the
# staff login, seeds demo data if empty, then starts the server — so the whole
# stack is self-configuring on `docker compose up`.
CMD ["sh", "entrypoint.sh"]
```

## 11. `backend/academics/__init__.py`

*1 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.
```

## 12. `backend/academics/apps.py`

*8 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

from django.apps import AppConfig


class AcademicsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "academics"
```

## 13. `backend/academics/management/commands/seed_demo_data.py`

*260 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

from datetime import date, time
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from academics.models import (
    Attendance,
    ClassSchedule,
    Course,
    CourseOffering,
    Department,
    Enrollment,
    ExamResult,
    ExamTimetable,
    Faculty,
    FeePayment,
    FeeStructure,
    Program,
    Room,
    Student,
)

# ---------------------------------------------------------------------------
# A small but internally CONSISTENT demo dataset. The earlier ad-hoc rows had
# every course pinned to Computer Science and left faculty/programs/fees/
# schedules empty, which made department questions wrong and left SQL-routed
# questions with nothing to return. This replaces all of that.
#
# Idempotent: wipes the academics tables and rebuilds from scratch, so it can
# be re-run any time to get back to a known-good state.
# ---------------------------------------------------------------------------

DEPARTMENTS = [
    {"name": "Computer Science", "code": "CS", "established_year": 1986},
    {"name": "Mathematics", "code": "MATH", "established_year": 1970},
    {"name": "Chemistry", "code": "CHEM", "established_year": 1965},
    {"name": "English", "code": "ENG", "established_year": 1960},
    {"name": "Commerce", "code": "COM", "established_year": 1972},
]

FACULTY = [
    {"first": "Alan", "last": "Turing", "dept": "CS", "designation": "Professor"},
    {"first": "Grace", "last": "Hopper", "dept": "CS", "designation": "Associate Professor"},
    {"first": "Emmy", "last": "Noether", "dept": "MATH", "designation": "Professor"},
    {"first": "Srinivasa", "last": "Ramanujan", "dept": "MATH", "designation": "Assistant Professor"},
    {"first": "Marie", "last": "Curie", "dept": "CHEM", "designation": "Professor"},
    {"first": "Virginia", "last": "Woolf", "dept": "ENG", "designation": "Associate Professor"},
    {"first": "Adam", "last": "Smith", "dept": "COM", "designation": "Professor"},
]

PROGRAMS = [
    {"name": "B.Tech Computer Science", "degree_level": "bachelor", "dept": "CS", "duration_years": 4},
    {"name": "M.Tech Computer Science", "degree_level": "master", "dept": "CS", "duration_years": 2},
    {"name": "B.Sc Mathematics", "degree_level": "bachelor", "dept": "MATH", "duration_years": 3},
    {"name": "B.Sc Chemistry", "degree_level": "bachelor", "dept": "CHEM", "duration_years": 3},
    {"name": "B.A English", "degree_level": "bachelor", "dept": "ENG", "duration_years": 3},
    {"name": "B.Com", "degree_level": "bachelor", "dept": "COM", "duration_years": 3},
]

COURSES = [
    {"code": "CS501", "title": "Machine Learning Fundamentals", "credits": 4, "dept": "CS",
     "description": "Covers supervised and unsupervised learning, neural networks, and model evaluation."},
    {"code": "CS310", "title": "Database Systems", "credits": 3, "dept": "CS",
     "description": "Relational algebra, SQL, normalization, transactions, and indexing."},
    {"code": "CS420", "title": "Operating Systems", "credits": 4, "dept": "CS",
     "description": "Processes, threads, scheduling, memory management, and file systems."},
    {"code": "MATH201", "title": "Linear Algebra", "credits": 4, "dept": "MATH",
     "description": "Vector spaces, matrices, eigenvalues, and linear transformations."},
    {"code": "MATH110", "title": "Calculus I", "credits": 4, "dept": "MATH",
     "description": "Limits, derivatives, integrals, and the fundamental theorem of calculus."},
    {"code": "CHEM210", "title": "Organic Chemistry I", "credits": 4, "dept": "CHEM",
     "description": "Structure, nomenclature, and reactions of organic compounds."},
    {"code": "ENG150", "title": "Shakespearean Literature", "credits": 3, "dept": "ENG",
     "description": "Close reading of major tragedies and comedies by William Shakespeare."},
    {"code": "COM220", "title": "Financial Accounting", "credits": 3, "dept": "COM",
     "description": "Principles of recording, summarizing, and reporting financial transactions."},
]

# course code -> list of prerequisite course codes
PREREQUISITES = {
    "CS501": ["MATH201"],  # ML builds on linear algebra
    "CS420": ["CS310"],
}

ROOMS = [
    {"building": "Main Building", "room_number": "101", "capacity": 60},
    {"building": "Main Building", "room_number": "102", "capacity": 40},
    {"building": "Science Block", "room_number": "201", "capacity": 50},
    {"building": "Science Block", "room_number": "202", "capacity": 30},
]

# course code -> (instructor "First Last", semester, section, day, start, end, building, room)
OFFERINGS = [
    {"course": "CS501", "instructor": "Alan Turing", "semester": "Fall 2026", "section": "A",
     "day": "mon", "start": time(10, 0), "end": time(11, 30), "building": "Main Building", "room": "101"},
    {"course": "CS310", "instructor": "Grace Hopper", "semester": "Fall 2026", "section": "A",
     "day": "tue", "start": time(9, 0), "end": time(10, 30), "building": "Main Building", "room": "102"},
    {"course": "CS420", "instructor": "Grace Hopper", "semester": "Fall 2026", "section": "A",
     "day": "thu", "start": time(14, 0), "end": time(15, 30), "building": "Main Building", "room": "102"},
    {"course": "MATH201", "instructor": "Emmy Noether", "semester": "Fall 2026", "section": "A",
     "day": "wed", "start": time(11, 0), "end": time(12, 30), "building": "Science Block", "room": "201"},
    {"course": "MATH110", "instructor": "Srinivasa Ramanujan", "semester": "Fall 2026", "section": "A",
     "day": "mon", "start": time(9, 0), "end": time(10, 30), "building": "Science Block", "room": "201"},
    {"course": "CHEM210", "instructor": "Marie Curie", "semester": "Fall 2026", "section": "A",
     "day": "fri", "start": time(10, 0), "end": time(11, 30), "building": "Science Block", "room": "202"},
    {"course": "ENG150", "instructor": "Virginia Woolf", "semester": "Fall 2026", "section": "A",
     "day": "tue", "start": time(13, 0), "end": time(14, 30), "building": "Main Building", "room": "101"},
    {"course": "COM220", "instructor": "Adam Smith", "semester": "Fall 2026", "section": "A",
     "day": "wed", "start": time(9, 0), "end": time(10, 30), "building": "Main Building", "room": "102"},
]

# course code -> (exam_date, start, end, building, room)
EXAMS = [
    {"course": "CS501", "date": date(2026, 12, 10), "start": time(9, 0), "end": time(12, 0),
     "building": "Main Building", "room": "101"},
    {"course": "CS310", "date": date(2026, 12, 12), "start": time(9, 0), "end": time(12, 0),
     "building": "Main Building", "room": "102"},
    {"course": "CS420", "date": date(2026, 12, 14), "start": time(9, 0), "end": time(12, 0),
     "building": "Main Building", "room": "102"},
    {"course": "MATH201", "date": date(2026, 12, 11), "start": time(9, 0), "end": time(12, 0),
     "building": "Science Block", "room": "201"},
    {"course": "MATH110", "date": date(2026, 12, 13), "start": time(9, 0), "end": time(12, 0),
     "building": "Science Block", "room": "201"},
    {"course": "CHEM210", "date": date(2026, 12, 15), "start": time(9, 0), "end": time(12, 0),
     "building": "Science Block", "room": "202"},
    {"course": "ENG150", "date": date(2026, 12, 16), "start": time(9, 0), "end": time(12, 0),
     "building": "Main Building", "room": "101"},
    {"course": "COM220", "date": date(2026, 12, 17), "start": time(9, 0), "end": time(12, 0),
     "building": "Main Building", "room": "102"},
]

# program name -> list of (semester, fee_type, amount)
FEES = [
    {"program": "B.Tech Computer Science", "semester": "Fall 2026", "fee_type": "Tuition", "amount": "75000.00"},
    {"program": "B.Tech Computer Science", "semester": "Fall 2026", "fee_type": "Lab", "amount": "10000.00"},
    {"program": "M.Tech Computer Science", "semester": "Fall 2026", "fee_type": "Tuition", "amount": "90000.00"},
    {"program": "B.Sc Mathematics", "semester": "Fall 2026", "fee_type": "Tuition", "amount": "45000.00"},
    {"program": "B.Sc Chemistry", "semester": "Fall 2026", "fee_type": "Tuition", "amount": "48000.00"},
    {"program": "B.Sc Chemistry", "semester": "Fall 2026", "fee_type": "Lab", "amount": "12000.00"},
    {"program": "B.A English", "semester": "Fall 2026", "fee_type": "Tuition", "amount": "40000.00"},
    {"program": "B.Com", "semester": "Fall 2026", "fee_type": "Tuition", "amount": "42000.00"},
]


class Command(BaseCommand):
    help = "Wipe and reseed the academics tables with a consistent demo dataset."

    def add_arguments(self, parser):
        parser.add_argument(
            "--if-empty",
            action="store_true",
            help=(
                "Only seed when there is no academics data yet. Use this on "
                "automated startup so a restart never wipes real data that was "
                "loaded after the first boot."
            ),
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options["if_empty"] and Department.objects.exists():
            self.stdout.write("Academics data already present; skipping seed (--if-empty).")
            return

        self._wipe()

        departments = {}
        for d in DEPARTMENTS:
            departments[d["code"]] = Department.objects.create(**d)

        faculty = {}
        for f in FACULTY:
            obj = Faculty.objects.create(
                first_name=f["first"],
                last_name=f["last"],
                email=f"{f['first'].lower()}.{f['last'].lower()}@college.edu",
                designation=f["designation"],
                department=departments[f["dept"]],
                joined_date=date(2015, 1, 1),
            )
            faculty[f"{f['first']} {f['last']}"] = obj

        programs = {}
        for p in PROGRAMS:
            programs[p["name"]] = Program.objects.create(
                name=p["name"],
                degree_level=p["degree_level"],
                department=departments[p["dept"]],
                duration_years=p["duration_years"],
            )

        courses = {}
        for c in COURSES:
            courses[c["code"]] = Course.objects.create(
                code=c["code"],
                title=c["title"],
                credits=c["credits"],
                department=departments[c["dept"]],
                description=c["description"],
            )
        # Wire prerequisites now that all courses exist.
        for code, prereqs in PREREQUISITES.items():
            courses[code].prerequisites.set([courses[p] for p in prereqs])

        rooms = {}
        for r in ROOMS:
            rooms[(r["building"], r["room_number"])] = Room.objects.create(**r)

        offerings = {}
        for o in OFFERINGS:
            offering = CourseOffering.objects.create(
                course=courses[o["course"]],
                instructor=faculty[o["instructor"]],
                semester=o["semester"],
                section=o["section"],
            )
            offerings[o["course"]] = offering
            ClassSchedule.objects.create(
                course_offering=offering,
                day_of_week=o["day"],
                start_time=o["start"],
                end_time=o["end"],
                room=rooms[(o["building"], o["room"])],
            )

        for e in EXAMS:
            ExamTimetable.objects.create(
                course=courses[e["course"]],
                exam_date=e["date"],
                start_time=e["start"],
                end_time=e["end"],
                room=rooms[(e["building"], e["room"])],
            )

        for fee in FEES:
            FeeStructure.objects.create(
                program=programs[fee["program"]],
                semester=fee["semester"],
                fee_type=fee["fee_type"],
                amount=Decimal(fee["amount"]),
            )

        self.stdout.write(self.style.SUCCESS(
            f"Seeded: {len(departments)} departments, {len(faculty)} faculty, "
            f"{len(programs)} programs, {len(courses)} courses, {len(rooms)} rooms, "
            f"{len(offerings)} offerings, {len(EXAMS)} exams, {len(FEES)} fee rows."
        ))

    def _wipe(self):
        # Delete children before parents to avoid FK violations. Per-student
        # tables are wiped too (they're empty, but keep this a clean reset).
        for model in (
            Attendance, ExamResult, Enrollment, FeePayment, Student,
            ClassSchedule, ExamTimetable, CourseOffering, FeeStructure,
            Course, Program, Faculty, Room, Department,
        ):
            model.objects.all().delete()
```

## 14. `backend/academics/management/commands/setup_readonly_role.py`

*70 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

import os

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

# The whitelist of tables the RAG agent's read-only role may SELECT from.
# General institutional data only — never the per-student tables. Kept in sync
# with db/sql/create_rag_agent_ro.sql and sync_worker/config.py.
ALLOWED_TABLES = [
    "departments",
    "faculty",
    "programs",
    "courses",
    "courses_prerequisites",
    "course_offerings",
    "rooms",
    "class_schedule",
    "exam_timetable",
    "fee_structure",
]


class Command(BaseCommand):
    help = (
        "Create or refresh the read-only 'rag_agent_ro' database role and its "
        "SELECT grants, idempotently, using the password from "
        "RAG_AGENT_RO_PASSWORD. Runs on backend startup so the whole stack "
        "comes up self-configured. Executes as the app's DB owner."
    )

    def handle(self, *args, **options):
        password = os.getenv("RAG_AGENT_RO_PASSWORD")
        if not password:
            raise CommandError("RAG_AGENT_RO_PASSWORD is not set; cannot create the read-only role.")

        db_name = connection.settings_dict["NAME"]
        pw_literal = password.replace("'", "''")  # escape single quotes for the SQL string literal
        grant_targets = ", ".join(f"public.{t}" for t in ALLOWED_TABLES)

        statements = [
            # Create the role only if it doesn't already exist.
            f"""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'rag_agent_ro') THEN
                    CREATE ROLE rag_agent_ro LOGIN PASSWORD '{pw_literal}';
                END IF;
            END
            $$;
            """,
            # Keep the password in sync with .env even if the role pre-existed.
            f"ALTER ROLE rag_agent_ro LOGIN PASSWORD '{pw_literal}';",
            "ALTER ROLE rag_agent_ro NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION CONNECTION LIMIT 10;",
            "ALTER ROLE rag_agent_ro SET default_transaction_read_only = on;",
            "REVOKE ALL ON SCHEMA public FROM PUBLIC;",
            f'GRANT CONNECT ON DATABASE "{db_name}" TO rag_agent_ro;',
            "GRANT USAGE ON SCHEMA public TO rag_agent_ro;",
            "REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM rag_agent_ro;",
            f"GRANT SELECT ON {grant_targets} TO rag_agent_ro;",
        ]

        with connection.cursor() as cur:
            for stmt in statements:
                cur.execute(stmt)

        self.stdout.write(self.style.SUCCESS(
            f"rag_agent_ro configured with SELECT on {len(ALLOWED_TABLES)} tables."
        ))
```

## 15. `backend/academics/migrations/0001_initial.py`

*245 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

# Generated by Django 5.2.16 on 2026-07-24 01:47

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Department',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=150, unique=True)),
                ('code', models.CharField(max_length=10, unique=True)),
                ('established_year', models.PositiveIntegerField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'db_table': 'departments',
            },
        ),
        migrations.CreateModel(
            name='Course',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(max_length=20, unique=True)),
                ('title', models.CharField(max_length=200)),
                ('credits', models.PositiveSmallIntegerField()),
                ('description', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('prerequisites', models.ManyToManyField(blank=True, related_name='required_for', to='academics.course')),
                ('department', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='courses', to='academics.department')),
            ],
            options={
                'db_table': 'courses',
            },
        ),
        migrations.CreateModel(
            name='CourseOffering',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('semester', models.CharField(max_length=20)),
                ('section', models.CharField(default='A', max_length=10)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('course', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='offerings', to='academics.course')),
            ],
            options={
                'db_table': 'course_offerings',
            },
        ),
        migrations.CreateModel(
            name='Enrollment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('active', 'Active'), ('completed', 'Completed'), ('dropped', 'Dropped')], default='active', max_length=20)),
                ('enrolled_on', models.DateField(auto_now_add=True)),
                ('course_offering', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='enrollments', to='academics.courseoffering')),
            ],
            options={
                'db_table': 'enrollments',
            },
        ),
        migrations.CreateModel(
            name='ExamResult',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('exam_type', models.CharField(max_length=50)),
                ('marks_obtained', models.DecimalField(decimal_places=2, max_digits=6)),
                ('max_marks', models.DecimalField(decimal_places=2, max_digits=6)),
                ('grade', models.CharField(blank=True, max_length=5)),
                ('enrollment', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='exam_results', to='academics.enrollment')),
            ],
            options={
                'db_table': 'exam_results',
            },
        ),
        migrations.CreateModel(
            name='Faculty',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('first_name', models.CharField(max_length=100)),
                ('last_name', models.CharField(max_length=100)),
                ('email', models.EmailField(max_length=254, unique=True)),
                ('phone', models.CharField(blank=True, max_length=20)),
                ('designation', models.CharField(blank=True, max_length=100)),
                ('joined_date', models.DateField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('department', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='faculty_members', to='academics.department')),
            ],
            options={
                'db_table': 'faculty',
            },
        ),
        migrations.AddField(
            model_name='courseoffering',
            name='instructor',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='course_offerings', to='academics.faculty'),
        ),
        migrations.CreateModel(
            name='Program',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=150)),
                ('degree_level', models.CharField(choices=[('bachelor', "Bachelor's"), ('master', "Master's"), ('diploma', 'Diploma'), ('phd', 'PhD')], max_length=20)),
                ('duration_years', models.PositiveSmallIntegerField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('department', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='programs', to='academics.department')),
            ],
            options={
                'db_table': 'programs',
            },
        ),
        migrations.CreateModel(
            name='FeeStructure',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('semester', models.CharField(max_length=20)),
                ('fee_type', models.CharField(max_length=50)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=10)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('program', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='fee_structures', to='academics.program')),
            ],
            options={
                'db_table': 'fee_structure',
            },
        ),
        migrations.CreateModel(
            name='Room',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('building', models.CharField(max_length=100)),
                ('room_number', models.CharField(max_length=20)),
                ('capacity', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'db_table': 'rooms',
                'unique_together': {('building', 'room_number')},
            },
        ),
        migrations.CreateModel(
            name='ExamTimetable',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('exam_date', models.DateField()),
                ('start_time', models.TimeField()),
                ('end_time', models.TimeField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('course', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='exam_slots', to='academics.course')),
                ('room', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='exam_slots', to='academics.room')),
            ],
            options={
                'db_table': 'exam_timetable',
            },
        ),
        migrations.CreateModel(
            name='ClassSchedule',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('day_of_week', models.CharField(choices=[('mon', 'Monday'), ('tue', 'Tuesday'), ('wed', 'Wednesday'), ('thu', 'Thursday'), ('fri', 'Friday'), ('sat', 'Saturday')], max_length=3)),
                ('start_time', models.TimeField()),
                ('end_time', models.TimeField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('course_offering', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='schedule_slots', to='academics.courseoffering')),
                ('room', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='class_schedules', to='academics.room')),
            ],
            options={
                'db_table': 'class_schedule',
            },
        ),
        migrations.CreateModel(
            name='Student',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('roll_number', models.CharField(max_length=20, unique=True)),
                ('first_name', models.CharField(max_length=100)),
                ('last_name', models.CharField(max_length=100)),
                ('email', models.EmailField(max_length=254, unique=True)),
                ('phone', models.CharField(blank=True, max_length=20)),
                ('date_of_birth', models.DateField(blank=True, null=True)),
                ('batch_year', models.PositiveIntegerField()),
                ('program', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='students', to='academics.program')),
            ],
            options={
                'db_table': 'students',
            },
        ),
        migrations.CreateModel(
            name='FeePayment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount_paid', models.DecimalField(decimal_places=2, max_digits=10)),
                ('payment_date', models.DateField()),
                ('status', models.CharField(default='paid', max_length=20)),
                ('fee_structure', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='payments', to='academics.feestructure')),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='fee_payments', to='academics.student')),
            ],
            options={
                'db_table': 'fee_payments',
            },
        ),
        migrations.AddField(
            model_name='enrollment',
            name='student',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='enrollments', to='academics.student'),
        ),
        migrations.CreateModel(
            name='Attendance',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField()),
                ('status', models.CharField(choices=[('present', 'Present'), ('absent', 'Absent'), ('excused', 'Excused')], max_length=10)),
                ('enrollment', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attendance_records', to='academics.enrollment')),
            ],
            options={
                'db_table': 'attendance',
                'unique_together': {('enrollment', 'date')},
            },
        ),
        migrations.AlterUniqueTogether(
            name='courseoffering',
            unique_together={('course', 'semester', 'section')},
        ),
        migrations.AlterUniqueTogether(
            name='enrollment',
            unique_together={('student', 'course_offering')},
        ),
    ]
```

## 16. `backend/academics/migrations/__init__.py`

*1 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.
```

## 17. `backend/academics/models.py`

*247 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

from django.db import models

# ============================================================================
# General institutional data — safe for the read-only RAG agent
# (rag_agent_ro is granted SELECT on these tables; see db/sql/create_rag_agent_ro.sql)
# ============================================================================


class Department(models.Model):
    name = models.CharField(max_length=150, unique=True)
    code = models.CharField(max_length=10, unique=True)
    established_year = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "departments"

    def __str__(self):
        return self.name


class Faculty(models.Model):
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True)
    designation = models.CharField(max_length=100, blank=True)
    department = models.ForeignKey(
        Department, on_delete=models.SET_NULL, null=True, related_name="faculty_members"
    )
    joined_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "faculty"

    def __str__(self):
        return f"{self.first_name} {self.last_name}"


class Program(models.Model):
    DEGREE_CHOICES = [
        ("bachelor", "Bachelor's"),
        ("master", "Master's"),
        ("diploma", "Diploma"),
        ("phd", "PhD"),
    ]
    name = models.CharField(max_length=150)
    degree_level = models.CharField(max_length=20, choices=DEGREE_CHOICES)
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name="programs")
    duration_years = models.PositiveSmallIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "programs"

    def __str__(self):
        return self.name


class Course(models.Model):
    code = models.CharField(max_length=20, unique=True)
    title = models.CharField(max_length=200)
    credits = models.PositiveSmallIntegerField()
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name="courses")
    description = models.TextField(blank=True)
    prerequisites = models.ManyToManyField(
        "self", symmetrical=False, blank=True, related_name="required_for"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "courses"

    def __str__(self):
        return f"{self.code} - {self.title}"


class Room(models.Model):
    building = models.CharField(max_length=100)
    room_number = models.CharField(max_length=20)
    capacity = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "rooms"
        unique_together = ("building", "room_number")

    def __str__(self):
        return f"{self.building} {self.room_number}"


class CourseOffering(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="offerings")
    instructor = models.ForeignKey(
        Faculty, on_delete=models.SET_NULL, null=True, related_name="course_offerings"
    )
    semester = models.CharField(max_length=20)
    section = models.CharField(max_length=10, default="A")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "course_offerings"
        unique_together = ("course", "semester", "section")

    def __str__(self):
        return f"{self.course.code} [{self.semester} {self.section}]"


class ClassSchedule(models.Model):
    DAY_CHOICES = [
        ("mon", "Monday"),
        ("tue", "Tuesday"),
        ("wed", "Wednesday"),
        ("thu", "Thursday"),
        ("fri", "Friday"),
        ("sat", "Saturday"),
    ]
    course_offering = models.ForeignKey(
        CourseOffering, on_delete=models.CASCADE, related_name="schedule_slots"
    )
    day_of_week = models.CharField(max_length=3, choices=DAY_CHOICES)
    start_time = models.TimeField()
    end_time = models.TimeField()
    room = models.ForeignKey(Room, on_delete=models.SET_NULL, null=True, related_name="class_schedules")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "class_schedule"

    def __str__(self):
        return f"{self.course_offering} {self.day_of_week} {self.start_time}-{self.end_time}"


class ExamTimetable(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="exam_slots")
    exam_date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    room = models.ForeignKey(Room, on_delete=models.SET_NULL, null=True, related_name="exam_slots")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "exam_timetable"

    def __str__(self):
        return f"{self.course.code} exam on {self.exam_date}"


class FeeStructure(models.Model):
    program = models.ForeignKey(Program, on_delete=models.CASCADE, related_name="fee_structures")
    semester = models.CharField(max_length=20)
    fee_type = models.CharField(max_length=50)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "fee_structure"

    def __str__(self):
        return f"{self.program} {self.semester} {self.fee_type}"


# ============================================================================
# Per-student data — NOT granted to rag_agent_ro. Personal/sensitive:
# identity, academic performance, attendance, and payment history.
# ============================================================================


class Student(models.Model):
    roll_number = models.CharField(max_length=20, unique=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    program = models.ForeignKey(Program, on_delete=models.SET_NULL, null=True, related_name="students")
    batch_year = models.PositiveIntegerField()

    class Meta:
        db_table = "students"

    def __str__(self):
        return f"{self.roll_number} - {self.first_name} {self.last_name}"


class Enrollment(models.Model):
    STATUS_CHOICES = [("active", "Active"), ("completed", "Completed"), ("dropped", "Dropped")]
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="enrollments")
    course_offering = models.ForeignKey(
        CourseOffering, on_delete=models.CASCADE, related_name="enrollments"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    enrolled_on = models.DateField(auto_now_add=True)

    class Meta:
        db_table = "enrollments"
        unique_together = ("student", "course_offering")

    def __str__(self):
        return f"{self.student.roll_number} -> {self.course_offering}"


class Attendance(models.Model):
    STATUS_CHOICES = [("present", "Present"), ("absent", "Absent"), ("excused", "Excused")]
    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name="attendance_records")
    date = models.DateField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)

    class Meta:
        db_table = "attendance"
        unique_together = ("enrollment", "date")


class ExamResult(models.Model):
    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name="exam_results")
    exam_type = models.CharField(max_length=50)
    marks_obtained = models.DecimalField(max_digits=6, decimal_places=2)
    max_marks = models.DecimalField(max_digits=6, decimal_places=2)
    grade = models.CharField(max_length=5, blank=True)

    class Meta:
        db_table = "exam_results"


class FeePayment(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="fee_payments")
    fee_structure = models.ForeignKey(
        FeeStructure, on_delete=models.SET_NULL, null=True, related_name="payments"
    )
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2)
    payment_date = models.DateField()
    status = models.CharField(max_length=20, default="paid")

    class Meta:
        db_table = "fee_payments"
```

## 18. `backend/accounts/__init__.py`

*1 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.
```

## 19. `backend/accounts/apps.py`

*8 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"
```

## 20. `backend/accounts/management/__init__.py`

*1 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.
```

## 21. `backend/accounts/management/commands/__init__.py`

*1 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.
```

## 22. `backend/accounts/management/commands/create_staff_user.py`

*26 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

import os

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create (or update) a staff user for accessing the assistant."

    def add_arguments(self, parser):
        parser.add_argument("--username", default=os.getenv("STAFF_USERNAME", "staff"))
        parser.add_argument("--password", default=os.getenv("STAFF_PASSWORD", "staffpass123"))

    def handle(self, *args, **options):
        username = options["username"]
        password = options["password"]

        user, created = User.objects.get_or_create(username=username)
        user.is_staff = True
        user.set_password(password)
        user.save()

        verb = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(f"{verb} staff user '{username}'."))
```

## 23. `backend/accounts/permissions.py`

*14 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

from rest_framework.permissions import BasePermission


class IsStaffUser(BasePermission):
    """Only authenticated users with is_staff=True. The assistant exposes
    college data and burns local-LLM compute, so it's staff-gated — a valid
    login alone isn't enough."""

    message = "Staff access required."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)
```

## 24. `backend/accounts/throttling.py`

*19 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

from rest_framework.throttling import UserRateThrottle


class AskRateThrottle(UserRateThrottle):
    """Per-user rate limit for the assistant endpoint.

    Each /api/ask/ call fans out into several CPU-bound local-LLM calls, so an
    unthrottled user (or a hijacked session) could saturate the server and deny
    service to everyone else. The rate itself lives in
    settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['ask'].

    Note: this uses Django's cache, which defaults to a per-process in-memory
    store. That's correct for the single backend process here; a multi-worker
    deployment would need a shared cache (e.g. Redis) for the limit to be global.
    """

    scope = "ask"
```

## 25. `backend/accounts/urls.py`

*12 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

from django.urls import path

from .views import csrf, login, logout, me

urlpatterns = [
    path("csrf/", csrf, name="csrf"),
    path("login/", login, name="login"),
    path("logout/", logout, name="logout"),
    path("me/", me, name="me"),
]
```

## 26. `backend/accounts/views.py`

*52 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

from django.contrib.auth import authenticate
from django.contrib.auth import login as django_login
from django.contrib.auth import logout as django_logout
from django.middleware.csrf import get_token
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def csrf(request):
    # Force CsrfViewMiddleware to set the csrftoken cookie so the SPA can read
    # it and send it back as the X-CSRFToken header on POSTs.
    get_token(request._request)
    return Response({"detail": "CSRF cookie set."})


@api_view(["POST"])
@authentication_classes([])  # login must work without a prior session/CSRF
@permission_classes([AllowAny])
def login(request):
    username = (request.data.get("username") or "").strip()
    password = request.data.get("password") or ""

    user = authenticate(request, username=username, password=password)
    if user is None:
        return Response({"error": "Invalid credentials."}, status=401)

    # Staff-only gate: a valid non-staff account still cannot get in.
    if not user.is_staff:
        return Response({"error": "This account is not authorized for staff access."}, status=403)

    # Establishes a server-side session and sets the httpOnly session cookie.
    django_login(request, user)
    return Response({"username": user.username, "is_staff": user.is_staff})


@api_view(["POST"])
def logout(request):
    django_logout(request)  # flushes the session
    return Response({"detail": "Logged out."})


@api_view(["GET"])
def me(request):
    # Requires an authenticated session (returns 403 otherwise), so the SPA
    # can ask "am I logged in?" on load.
    return Response({"username": request.user.username, "is_staff": request.user.is_staff})
```

## 27. `backend/audit/__init__.py`

*1 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.
```

## 28. `backend/audit/apps.py`

*8 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

from django.apps import AppConfig


class AuditConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "audit"
```

## 29. `backend/audit/migrations/0001_initial.py`

*36 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

# Generated by Django 5.2.16 on 2026-07-24 08:59

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='AuditLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('username', models.CharField(db_index=True, max_length=150)),
                ('client_ip', models.GenericIPAddressField(blank=True, null=True)),
                ('question', models.TextField()),
                ('route', models.CharField(blank=True, max_length=10)),
                ('agents_used', models.CharField(blank=True, max_length=20)),
                ('generated_sql', models.TextField(blank=True, null=True)),
                ('final_answer', models.TextField(blank=True)),
                ('injection_flags', models.TextField(blank=True)),
                ('latency_ms', models.FloatField(blank=True, null=True)),
            ],
            options={
                'db_table': 'audit_log',
                'ordering': ['-created_at'],
            },
        ),
    ]
```

## 30. `backend/audit/migrations/__init__.py`

*1 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.
```

## 31. `backend/audit/models.py`

*30 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

from django.db import models


class AuditLog(models.Model):
    """One row per question asked through /api/ask/ — who asked, which agent(s)
    handled it, the exact SQL run (if any), and the final answer. Separate from
    verification_logs (which is claim-level fact-checking); this is
    request-level accountability for a system sitting over institutional data.
    """

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    username = models.CharField(max_length=150, db_index=True)
    client_ip = models.GenericIPAddressField(null=True, blank=True)

    question = models.TextField()  # already sanitized before storage
    route = models.CharField(max_length=10, blank=True)  # SQL / RAG / BOTH
    agents_used = models.CharField(max_length=20, blank=True)
    generated_sql = models.TextField(null=True, blank=True)
    final_answer = models.TextField(blank=True)
    injection_flags = models.TextField(blank=True)  # sanitizer flags, if any
    latency_ms = models.FloatField(null=True, blank=True)

    class Meta:
        db_table = "audit_log"
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.created_at:%Y-%m-%d %H:%M}] {self.username}: {self.question[:50]}"
```

## 32. `backend/common/__init__.py`

*1 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.
```

## 33. `backend/common/exceptions.py`

*35 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

class ServiceUnavailable(Exception):
    """A backing service (LLM, database, vector store) is unreachable or failing.

    Carries a `user_message` that is SAFE to show an end user — plain, no stack
    traces, no raw connection strings — while the original technical detail
    stays in `args`/logs for operators. The orchestrator catches these to
    degrade gracefully; the API layer maps them to the user_message.
    """

    service = "system"
    user_message = "The system is temporarily unavailable. Please try again in a moment."

    def __init__(self, detail=None):
        super().__init__(detail or self.user_message)


class LLMUnavailable(ServiceUnavailable):
    service = "llm"
    user_message = (
        "The AI service is temporarily unavailable. Please try again in a moment."
    )


class DatabaseUnavailable(ServiceUnavailable):
    service = "database"
    user_message = (
        "The information service is temporarily unavailable. Please try again in a moment."
    )


class VectorStoreUnavailable(ServiceUnavailable):
    service = "vector_store"
    user_message = "Descriptive search is temporarily unavailable."
```

## 34. `backend/common/ollama.py`

*78 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

import json
import os

import requests

from common.exceptions import LLMUnavailable

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")

# (connect, read) timeouts. A short CONNECT timeout means a DOWN Ollama fails
# fast (~5s) instead of hanging. The READ timeout bounds a SLOW Ollama: even if
# it accepts the connection but stalls, the request gives up rather than
# hanging forever. Both are env-tunable.
CONNECT_TIMEOUT = float(os.getenv("OLLAMA_CONNECT_TIMEOUT", "5"))
READ_TIMEOUT = float(os.getenv("OLLAMA_READ_TIMEOUT", "120"))
_TIMEOUT = (CONNECT_TIMEOUT, READ_TIMEOUT)


def chat(model, messages, options=None, response_format=None):
    """Non-streaming chat. Returns the assistant message content string.
    Raises LLMUnavailable if Ollama is unreachable, times out, or errors."""
    payload = {"model": model, "messages": messages, "stream": False, "options": options or {}}
    if response_format is not None:
        payload["format"] = response_format
    try:
        resp = requests.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload, timeout=_TIMEOUT)
        resp.raise_for_status()
        return resp.json()["message"]["content"]
    except requests.RequestException as exc:
        raise LLMUnavailable(f"Ollama chat request failed: {exc}") from exc


def chat_stream(model, messages, options=None):
    """Streaming chat. Yields content pieces as they arrive. Raises
    LLMUnavailable on any failure, including the stream dropping mid-answer."""
    payload = {"model": model, "messages": messages, "stream": True, "options": options or {}}
    try:
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/chat", json=payload, timeout=_TIMEOUT, stream=True
        )
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line:
                continue
            chunk = json.loads(line)
            piece = chunk.get("message", {}).get("content", "")
            if piece:
                yield piece
            if chunk.get("done"):
                break
    except requests.RequestException as exc:
        raise LLMUnavailable(f"Ollama streaming chat failed: {exc}") from exc


def embeddings(model, prompt):
    """Returns an embedding vector. Raises LLMUnavailable on failure."""
    try:
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/embeddings",
            json={"model": model, "prompt": prompt},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()["embedding"]
    except requests.RequestException as exc:
        raise LLMUnavailable(f"Ollama embeddings request failed: {exc}") from exc


def ping(timeout=3):
    """Lightweight liveness probe for the health endpoint. Returns True if
    Ollama responds, False otherwise (never raises)."""
    try:
        resp = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=timeout)
        return resp.status_code == 200
    except requests.RequestException:
        return False
```

## 35. `backend/config/__init__.py`

*1 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.
```

## 36. `backend/config/asgi.py`

*9 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_asgi_application()
```

## 37. `backend/config/settings.py`

*182 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-insecure-secret-key-change-me")
DEBUG = os.getenv("DJANGO_DEBUG", "true").lower() == "true"
ALLOWED_HOSTS = os.getenv("DJANGO_ALLOWED_HOSTS", "*").split(",")

# The public host/IP the assistant is reached at (behind the HTTPS proxy).
SERVER_HOST = os.getenv("SERVER_HOST", "localhost")

# --- HTTPS / cookie hardening -------------------------------------------------
# The stack sits behind the Caddy reverse proxy, which terminates TLS and
# forwards X-Forwarded-Proto so Django knows the original request was HTTPS.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Turn on Secure cookies once served over HTTPS (default on). Set
# COOKIE_SECURE=false only if you deliberately run plain HTTP.
_cookie_secure = os.getenv("COOKIE_SECURE", "true").lower() == "true"
SESSION_COOKIE_SECURE = _cookie_secure
CSRF_COOKIE_SECURE = _cookie_secure
SESSION_COOKIE_HTTPONLY = True  # session cookie is never readable by JavaScript
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

# The browser reaches the SPA + API through the proxy over HTTPS, so that
# origin must be trusted for CSRF-protected POSTs.
CSRF_TRUSTED_ORIGINS = [
    f"https://{SERVER_HOST}",
    "https://localhost",
]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework.authtoken",
    "corsheaders",
    "accounts",
    "health",
    "academics",
    "sql_agent",
    "rag_agent",
    "router_agent",
    "synthesis_agent",
    "verification_agent",
    "orchestrator",
    "experiments",
    "audit",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("POSTGRES_DB", "college_rag"),
        "USER": os.getenv("POSTGRES_USER", "postgres"),
        "PASSWORD": os.getenv("POSTGRES_PASSWORD", "postgres"),
        "HOST": os.getenv("POSTGRES_HOST", "postgres"),
        "PORT": os.getenv("POSTGRES_PORT", "5432"),
    }
}

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    # Session-cookie auth (httpOnly, CSRF-protected) rather than a token the
    # browser stores in localStorage where injected JS could read it.
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    # Everything requires an authenticated session unless it explicitly opts
    # out (login/csrf). /api/ask/ further narrows this to staff.
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    # Per-user rate limits. The 'ask' scope is applied by AskRateThrottle on
    # the assistant endpoint (see accounts/throttling.py).
    "DEFAULT_THROTTLE_RATES": {
        "ask": "10/min",
    },
}

# Dev-only: allow the Vite dev server to call the API from the browser.
CORS_ALLOW_ALL_ORIGINS = DEBUG
CORS_ALLOWED_ORIGINS = os.getenv("CORS_ALLOWED_ORIGINS", "").split(",") if not DEBUG else []

# Ollama / Qdrant connection info, used by sql_agent and (later) other RAG code.
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")

# Ensures sql_agent's "log every generated query before execution" requirement
# is actually visible: Django's default logging only surfaces WARNING+ for
# unconfigured loggers, which would silently swallow the INFO-level audit log.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "loggers": {
        "sql_agent": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "rag_agent": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "router_agent": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "synthesis_agent": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "verification_agent": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "orchestrator": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}
```

## 38. `backend/config/urls.py`

*9 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

from django.urls import include, path

urlpatterns = [
    path("api/health/", include("health.urls")),
    path("api/auth/", include("accounts.urls")),
    path("api/ask/", include("orchestrator.urls")),
]
```

## 39. `backend/config/wsgi.py`

*9 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_wsgi_application()
```

## 40. `backend/entrypoint.sh`

*22 lines*

```bash
#!/bin/sh
# Copyright (c) 2026 Yash Garad. All rights reserved.
# Backend startup: bring the database to a ready state, then serve.
# Every step here is idempotent, so it is safe to run on every container start.
set -e

echo "[entrypoint] Applying database migrations..."
python manage.py migrate --noinput

echo "[entrypoint] Configuring read-only database role (rag_agent_ro)..."
python manage.py setup_readonly_role

echo "[entrypoint] Ensuring staff login exists..."
python manage.py create_staff_user

if [ "${SEED_DEMO_DATA:-true}" = "true" ]; then
  echo "[entrypoint] Seeding demo data (only if the database is empty)..."
  python manage.py seed_demo_data --if-empty
fi

echo "[entrypoint] Starting web server on port 8000..."
exec python manage.py runserver 0.0.0.0:8000
```

## 41. `backend/experiments/__init__.py`

*1 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.
```

## 42. `backend/experiments/apps.py`

*8 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

from django.apps import AppConfig


class ExperimentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "experiments"
```

## 43. `backend/experiments/fixtures/sample_qa.json`

*42 lines*

```json
[
  {
    "question": "How many credits is the Operating Systems course worth?",
    "answer": "The Operating Systems course (CS420) is worth 4 credits."
  },
  {
    "question": "What does the Database Systems course cover?",
    "answer": "Database Systems (CS310) covers relational algebra, SQL, normalization, transactions, and indexing. It is worth 3 credits."
  },
  {
    "question": "Which department offers the Organic Chemistry course?",
    "answer": "Organic Chemistry I (CHEM210) is offered by the Chemistry department."
  },
  {
    "question": "When was the English department established?",
    "answer": "The English department (code ENG) was established in 1960."
  },
  {
    "question": "Who teaches the Machine Learning Fundamentals course?",
    "answer": "Machine Learning Fundamentals (CS501) is taught by Alan Turing, a Professor in the Computer Science department."
  },
  {
    "question": "What is the tuition fee for the B.Tech Computer Science program?",
    "answer": "The B.Tech Computer Science program has a tuition fee of 75000 for Fall 2026, plus a 10000 lab fee."
  },
  {
    "question": "What are the prerequisites for Machine Learning Fundamentals?",
    "answer": "Machine Learning Fundamentals (CS501) requires Linear Algebra (MATH201) as a prerequisite."
  },
  {
    "question": "When is the final exam for Database Systems?",
    "answer": "The final exam for Database Systems (CS310) is on December 12, 2026, from 9:00 AM to 12:00 PM."
  },
  {
    "question": "What topics are covered in the Linear Algebra course?",
    "answer": "Linear Algebra (MATH201) covers vector spaces, matrices, eigenvalues, and linear transformations. It is worth 4 credits."
  },
  {
    "question": "How long is the M.Tech Computer Science program?",
    "answer": "The M.Tech Computer Science program is a 2-year master's degree program in the Computer Science department."
  }
]
```

## 44. `backend/experiments/management/__init__.py`

*1 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.
```

## 45. `backend/experiments/management/commands/__init__.py`

*1 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.
```

## 46. `backend/experiments/management/commands/load_test.py`

*176 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

import json
import os
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from django.core.management.base import BaseCommand, CommandError

DEFAULT_QA_PATH = "experiments/fixtures/sample_qa.json"


class Command(BaseCommand):
    help = (
        "Fires N concurrent questions at /api/ask/ over real HTTP and reports "
        "response-time statistics — time-to-first-token (TTFT) and total time "
        "to stream the full answer — so you can see how latency behaves when "
        "multiple management users hit the assistant simultaneously."
    )

    def add_arguments(self, parser):
        parser.add_argument("--concurrency", type=int, default=20, help="Number of simultaneous requests.")
        parser.add_argument("--base-url", default="http://localhost:8000", help="Backend base URL.")
        parser.add_argument("--username", default=os.getenv("STAFF_USERNAME", "staff"))
        parser.add_argument("--password", default=os.getenv("STAFF_PASSWORD", "staffpass123"))
        parser.add_argument("--qa-file", default=DEFAULT_QA_PATH, help="Question source (cycled to fill concurrency).")
        parser.add_argument("--timeout", type=int, default=600, help="Per-request timeout (seconds).")

    def handle(self, *args, **options):
        base_url = options["base_url"].rstrip("/")
        token = self._login(base_url, options["username"], options["password"])
        questions = self._questions(options["qa_file"], options["concurrency"])
        n = len(questions)

        self.stdout.write(self.style.MIGRATE_HEADING(
            f"Firing {n} concurrent requests at {base_url}/api/ask/"
        ))

        wall_start = time.perf_counter()
        results = [None] * n
        with ThreadPoolExecutor(max_workers=n) as pool:
            futures = {
                pool.submit(self._one_request, base_url, token, q, options["timeout"], i): i
                for i, q in enumerate(questions)
            }
            for fut in as_completed(futures):
                i = futures[fut]
                results[i] = fut.result()
        wall_total = time.perf_counter() - wall_start

        self._report(results, wall_total)

    def _login(self, base_url, username, password):
        try:
            resp = requests.post(
                f"{base_url}/api/auth/login/",
                json={"username": username, "password": password},
                timeout=30,
            )
        except requests.RequestException as exc:
            raise CommandError(f"could not reach backend to log in: {exc}")
        if resp.status_code != 200:
            raise CommandError(f"login failed ({resp.status_code}): {resp.text[:200]}")
        return resp.json()["token"]

    def _questions(self, path, concurrency):
        if not os.path.exists(path):
            raise CommandError(f"QA file not found: {path}")
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        pool = [item["question"] for item in data]
        if not pool:
            raise CommandError("QA file has no questions.")
        # Cycle through the available questions to reach the requested count.
        return [pool[i % len(pool)] for i in range(concurrency)]

    def _one_request(self, base_url, token, question, timeout, idx):
        result = {
            "idx": idx,
            "question": question,
            "ok": False,
            "status": None,
            "ttft_ms": None,
            "total_ms": None,
            "tokens": 0,
            "error": None,
        }
        start = time.perf_counter()
        try:
            resp = requests.post(
                f"{base_url}/api/ask/",
                headers={"Authorization": f"Token {token}", "Content-Type": "application/json"},
                json={"question": question},
                stream=True,
                timeout=timeout,
            )
            result["status"] = resp.status_code
            if resp.status_code != 200:
                result["error"] = resp.text[:200]
                return result

            first_token_at = None
            saw_error = False
            error_msg = None
            expecting = None  # tracks the event: of the frame whose data: is next
            for raw in resp.iter_lines():
                if not raw:
                    continue
                line = raw.decode("utf-8", errors="replace")
                if line.startswith("event:"):
                    expecting = line[len("event:"):].strip()
                    if expecting == "token" and first_token_at is None:
                        first_token_at = time.perf_counter()
                elif line.startswith("data:"):
                    if expecting == "token" and '"text"' in line:
                        result["tokens"] += 1
                    elif expecting == "error":
                        # The pipeline can stream a server-side error mid-stream
                        # (HTTP is already 200 by then) — a 0-token "success"
                        # would otherwise hide a real under-load failure.
                        saw_error = True
                        error_msg = line[len("data:"):].strip()[:200]

            end = time.perf_counter()
            result["ttft_ms"] = round((first_token_at - start) * 1000, 1) if first_token_at else None
            result["total_ms"] = round((end - start) * 1000, 1)
            if saw_error:
                result["error"] = f"stream error event: {error_msg}"
                result["ok"] = False
            elif result["tokens"] == 0:
                result["error"] = "no tokens streamed (empty answer)"
                result["ok"] = False
            else:
                result["ok"] = True
        except requests.RequestException as exc:
            result["error"] = str(exc)
            result["total_ms"] = round((time.perf_counter() - start) * 1000, 1)
        return result

    def _report(self, results, wall_total):
        self.stdout.write(self.style.MIGRATE_HEADING("\nPer-request results:"))
        self.stdout.write(f"  {'#':>3} {'status':>6} {'TTFT(ms)':>10} {'total(ms)':>11} {'tokens':>7}  question")
        for r in sorted(results, key=lambda x: x["idx"]):
            flag = "" if r["ok"] else f"  ERROR: {r['error']}"
            ttft = r["ttft_ms"] if r["ttft_ms"] is not None else "-"
            self.stdout.write(
                f"  {r['idx']:>3} {str(r['status']):>6} {str(ttft):>10} "
                f"{str(r['total_ms']):>11} {r['tokens']:>7}  {r['question'][:45]}{flag}"
            )

        ok = [r for r in results if r["ok"]]
        failed = [r for r in results if not r["ok"]]

        self.stdout.write(self.style.MIGRATE_HEADING("\n=== Summary ==="))
        self.stdout.write(f"  requests:      {len(results)}  (ok={len(ok)}, failed={len(failed)})")
        self.stdout.write(f"  wall-clock:    {wall_total * 1000:.0f} ms for the whole batch")

        if ok:
            self._stat_block("time-to-first-token (TTFT)", [r["ttft_ms"] for r in ok if r["ttft_ms"] is not None])
            self._stat_block("total response time", [r["total_ms"] for r in ok])
            throughput = len(ok) / wall_total if wall_total else 0
            self.stdout.write(f"\n  throughput:    {throughput:.2f} completed requests/sec under load")

        if failed:
            self.stdout.write(self.style.ERROR(f"\n  {len(failed)} request(s) failed — see per-request rows above."))

    def _stat_block(self, label, values):
        if not values:
            return
        vals = sorted(values)
        p95 = vals[min(len(vals) - 1, int(round(0.95 * (len(vals) - 1))))]
        self.stdout.write(f"\n  {label}:")
        self.stdout.write(f"    min={min(vals):.0f}  mean={statistics.mean(vals):.0f}  "
                          f"median={statistics.median(vals):.0f}  p95={p95:.0f}  max={max(vals):.0f}  (ms)")
```

## 47. `backend/experiments/management/commands/run_experiment.py`

*160 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

import csv
import json
import os
from datetime import datetime, timezone

from django.core.management.base import BaseCommand, CommandError

from experiments import runner, similarity
from experiments.warmup import warm_up_models

DEFAULT_QA_PATH = "experiments/fixtures/sample_qa.json"
DEFAULT_OUTPUT_DIR = "experiment_results"


class Command(BaseCommand):
    help = (
        "Runs a set of ground-truth Q/A pairs through the full pipeline under "
        "three configurations (full swarm, RAG-only, SQL-only), scores each "
        "answer against ground truth, and exports per-run results to CSV "
        "(plus a JSONL sidecar with the full nested detail). Results are "
        "written incrementally so a long run survives interruption."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--qa-file",
            default=DEFAULT_QA_PATH,
            help="Path to a JSON file: [{\"question\": ..., \"answer\": ...}, ...]",
        )
        parser.add_argument(
            "--configs",
            default=",".join(runner.CONFIGS),
            help=f"Comma-separated subset of: {', '.join(runner.CONFIGS)}",
        )
        parser.add_argument(
            "--threshold",
            type=float,
            default=similarity.DEFAULT_THRESHOLD,
            help="Semantic-similarity threshold for marking an answer correct.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Only run the first N Q/A pairs (handy for a quick smoke test).",
        )
        parser.add_argument(
            "--output-dir",
            default=DEFAULT_OUTPUT_DIR,
            help="Directory for the CSV + JSONL outputs.",
        )
        parser.add_argument(
            "--tag",
            default=None,
            help="Optional label included in the output filenames.",
        )
        parser.add_argument(
            "--no-warmup",
            action="store_true",
            help="Skip the model warm-up pass (leave cold-start time in latency).",
        )

    def handle(self, *args, **options):
        qa_pairs = self._load_qa(options["qa_file"])
        if options["limit"]:
            qa_pairs = qa_pairs[: options["limit"]]

        configs = [c.strip() for c in options["configs"].split(",") if c.strip()]
        for c in configs:
            if c not in runner.CONFIGS:
                raise CommandError(f"unknown config {c!r}; valid: {', '.join(runner.CONFIGS)}")

        os.makedirs(options["output_dir"], exist_ok=True)
        # timezone.utc rather than Date.now-style calls; deterministic-ish name.
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        tag = f"_{options['tag']}" if options["tag"] else ""
        csv_path = os.path.join(options["output_dir"], f"experiment{tag}_{stamp}.csv")
        jsonl_path = os.path.join(options["output_dir"], f"experiment{tag}_{stamp}.jsonl")

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"Running {len(qa_pairs)} Q/A pairs x {len(configs)} configs "
                f"= {len(qa_pairs) * len(configs)} pipeline runs"
            )
        )
        self.stdout.write(f"  configs: {', '.join(configs)}")
        self.stdout.write(f"  threshold: {options['threshold']}")
        self.stdout.write(f"  CSV:   {csv_path}")
        self.stdout.write(f"  JSONL: {jsonl_path}\n")

        if not options["no_warmup"]:
            self.stdout.write("Warming up models (excluded from latency)…")
            warm_up_models()

        # Per-config running tallies for the end-of-run summary.
        tally = {c: {"total": 0, "correct": 0, "latency_ms": [], "verif_fail": 0} for c in configs}

        with open(csv_path, "w", newline="", encoding="utf-8") as csv_file, \
                open(jsonl_path, "w", encoding="utf-8") as jsonl_file:
            writer = csv.DictWriter(csv_file, fieldnames=runner.CSV_COLUMNS, extrasaction="ignore")
            writer.writeheader()

            for i, pair in enumerate(qa_pairs, 1):
                question = pair["question"]
                ground_truth = pair["answer"]
                for config in configs:
                    row = runner.run_one(config, question, ground_truth, threshold=options["threshold"])

                    writer.writerow(row)
                    csv_file.flush()  # survive interruption mid-run
                    jsonl_file.write(json.dumps(row) + "\n")
                    jsonl_file.flush()

                    t = tally[config]
                    t["total"] += 1
                    t["correct"] += 1 if row["correct"] == "yes" else 0
                    if row["latency_ms"] is not None:
                        t["latency_ms"].append(row["latency_ms"])
                    if row["verification_flag"] == "fail":
                        t["verif_fail"] += 1

                    flag = "OK " if row["correct"] == "yes" else "XX "
                    err = f"  ERROR: {row['error']}" if row["error"] else ""
                    self.stdout.write(
                        f"  [{i}/{len(qa_pairs)}] {config:<9} {flag} "
                        f"route={row['route_used']} sim={row['semantic_similarity']} "
                        f"verif={row['verification_flag']} {row['latency_ms']}ms{err}"
                    )

        self._print_summary(tally, csv_path)

    def _load_qa(self, path):
        if not os.path.exists(path):
            raise CommandError(
                f"QA file not found: {path}. Provide one with --qa-file pointing to a JSON "
                'list of {"question": ..., "answer": ...} objects.'
            )
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list) or not data:
            raise CommandError("QA file must be a non-empty JSON list.")
        for i, item in enumerate(data):
            if "question" not in item or "answer" not in item:
                raise CommandError(f"QA item {i} is missing 'question' or 'answer'.")
        return data

    def _print_summary(self, tally, csv_path):
        self.stdout.write(self.style.MIGRATE_HEADING("\n=== Summary by configuration ==="))
        for config, t in tally.items():
            n = t["total"] or 1
            acc = 100.0 * t["correct"] / n
            lat = t["latency_ms"]
            avg_lat = sum(lat) / len(lat) if lat else 0
            self.stdout.write(
                f"  {config:<9} accuracy={acc:5.1f}% ({t['correct']}/{t['total']})  "
                f"avg_latency={avg_lat:8.0f}ms  verification_fails={t['verif_fail']}"
            )
        self.stdout.write(self.style.SUCCESS(f"\nWrote results to {csv_path}"))
```

## 48. `backend/experiments/runner.py`

*205 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

import time
from concurrent.futures import ThreadPoolExecutor

from rag_agent.service import retrieve
from router_agent.classifier import classify
from sql_agent.service import ask as sql_ask
from synthesis_agent.service import synthesize_answer
from verification_agent.service import verify_and_correct

from . import similarity

# The three configurations being compared.
#   full      -> the swarm as built: the router picks SQL / RAG / BOTH.
#   rag_only  -> ablation: force RAG, never call the SQL agent.
#   sql_only  -> ablation: force SQL, never call the RAG agent.
CONFIGS = ("full", "rag_only", "sql_only")

RAG_TOP_K = 5


def _resolve_route(config, question):
    if config == "rag_only":
        return "RAG", "forced RAG (ablation)"
    if config == "sql_only":
        return "SQL", "forced SQL (ablation)"
    # full: use the real router, mirroring the orchestrator's BOTH fallback.
    rr = classify(question)
    if rr.error:
        return "BOTH", f"router error ({rr.error}); defaulted to BOTH"
    return rr.route, rr.reason


def _gather_sources(route, question):
    """Runs SQL and/or RAG per the route, in parallel when both are needed —
    same concurrency the orchestrator uses, so latency is representative."""
    sql_result = None
    rag_chunks = None
    needs_sql = route in ("SQL", "BOTH")
    needs_rag = route in ("RAG", "BOTH")

    if needs_sql and needs_rag:
        with ThreadPoolExecutor(max_workers=2) as pool:
            sql_future = pool.submit(sql_ask, question, True)
            rag_future = pool.submit(retrieve, question, RAG_TOP_K)
            sql_result = sql_future.result()
            rag_chunks = rag_future.result()
    elif needs_sql:
        sql_result = sql_ask(question, execute=True)
    elif needs_rag:
        rag_chunks = retrieve(question, top_k=RAG_TOP_K)

    return sql_result, rag_chunks


def _agents_used(route):
    return {
        "SQL": "sql",
        "RAG": "rag",
        "BOTH": "sql+rag",
    }.get(route, route.lower())


def _verification_flag(claims, errored):
    if errored:
        return "error"
    if not claims:
        return "na"
    flagged = [c for c in claims if not c["supported"]]
    return "fail" if flagged else "pass"


def run_one(config, question, ground_truth, threshold=similarity.DEFAULT_THRESHOLD):
    """Runs a single (config, question) through router -> SQL/RAG -> synthesis
    -> verification, timing each stage and comparing to ground truth. Returns
    a flat dict of everything worth logging. Never raises: any failure is
    captured in the 'error' field and the row is marked incorrect."""
    row = {
        "question": question,
        "config_used": config,
        "ground_truth_answer": ground_truth,
        "route_used": None,
        "route_reason": None,
        "agents_used": None,
        "generated_sql": None,
        "sql_row_count": None,
        "sql_error": None,
        "rag_chunk_count": None,
        "rag_top_score": None,
        "rag_chunks": None,
        "synthesis_answer": None,
        "final_answer": None,
        "verification_flag": "na",
        "verification_claims_total": 0,
        "verification_flagged_count": 0,
        "verification_was_corrected": False,
        "semantic_similarity": None,
        "string_similarity": None,
        "correctness_basis": None,
        "correct": "no",
        "correct_post_verification": "no",
        "pipeline_ms": None,
        "verification_ms": None,
        "latency_ms": None,
        "error": None,
    }

    t_start = time.perf_counter()
    try:
        route, reason = _resolve_route(config, question)
        row["route_used"] = route
        row["route_reason"] = reason
        row["agents_used"] = _agents_used(route)

        sql_result, rag_chunks = _gather_sources(route, question)

        if sql_result is not None:
            row["generated_sql"] = sql_result.generated_sql
            row["sql_error"] = sql_result.error
            row["sql_row_count"] = len(sql_result.rows) if sql_result.rows else 0
        if rag_chunks is not None:
            row["rag_chunk_count"] = len(rag_chunks)
            row["rag_top_score"] = round(rag_chunks[0].score, 4) if rag_chunks else None
            row["rag_chunks"] = " | ".join(
                f"{c.table}#{c.row_id}({c.score:.3f}): {c.text}" for c in rag_chunks
            )

        synthesis_answer = synthesize_answer(question, route, sql_result=sql_result, rag_chunks=rag_chunks)
        row["synthesis_answer"] = synthesis_answer
        pipeline_ms = (time.perf_counter() - t_start) * 1000
        row["pipeline_ms"] = round(pipeline_ms, 1)

        # Verification pass (not in the live /api/ask/ pipeline, but part of
        # what this experiment measures per the spec).
        verif_errored = False
        t_verif = time.perf_counter()
        try:
            vresult = verify_and_correct(question, route, synthesis_answer, sql_result=sql_result, rag_chunks=rag_chunks)
            row["verification_claims_total"] = len(vresult.claims)
            row["verification_flagged_count"] = sum(1 for c in vresult.claims if not c["supported"])
            row["verification_was_corrected"] = vresult.was_corrected
            row["final_answer"] = vresult.final_answer
        except Exception as exc:  # verification is best-effort; don't lose the row
            verif_errored = True
            row["final_answer"] = synthesis_answer
            row["error"] = f"verification failed: {exc}"
        row["verification_ms"] = round((time.perf_counter() - t_verif) * 1000, 1)
        row["verification_flag"] = _verification_flag(
            [] if verif_errored else vresult.claims, verif_errored
        )

        row["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 1)

        # Correctness is scored on the synthesis answer — that's the system's
        # actual output "as built" (verification isn't deployed in /api/ask/).
        # We also score the post-verification answer separately for comparison.
        score = similarity.score_answer(synthesis_answer, ground_truth, threshold=threshold)
        row["semantic_similarity"] = score["semantic_similarity"]
        row["string_similarity"] = score["string_similarity"]
        row["correctness_basis"] = score["correctness_basis"]
        row["correct"] = "yes" if score["correct"] else "no"

        post_score = similarity.score_answer(row["final_answer"] or synthesis_answer, ground_truth, threshold=threshold)
        row["correct_post_verification"] = "yes" if post_score["correct"] else "no"

    except Exception as exc:
        row["error"] = str(exc)
        row["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 1)

    return row


# Column order for CSV export. The five columns the spec explicitly requires
# come first; everything else follows so nothing relevant is lost.
CSV_COLUMNS = [
    "question",
    "config_used",
    "correct",
    "latency_ms",
    "verification_flag",
    # --- everything else worth capturing for the paper ---
    "route_used",
    "agents_used",
    "semantic_similarity",
    "string_similarity",
    "correctness_basis",
    "correct_post_verification",
    "generated_sql",
    "sql_row_count",
    "sql_error",
    "rag_chunk_count",
    "rag_top_score",
    "verification_claims_total",
    "verification_flagged_count",
    "verification_was_corrected",
    "pipeline_ms",
    "verification_ms",
    "route_reason",
    "final_answer",
    "synthesis_answer",
    "ground_truth_answer",
    "rag_chunks",
    "error",
]
```

## 49. `backend/experiments/similarity.py`

*61 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

import math
import re
from difflib import SequenceMatcher

from rag_agent.embedder import embed_text

DEFAULT_THRESHOLD = 0.75


def _cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _normalize(text):
    return re.sub(r"\s+", " ", (text or "").lower().strip())


def string_similarity(a, b):
    """Cheap lexical overlap via difflib — a secondary signal alongside the
    semantic score, useful for spotting cases where the wording matches
    closely vs cases where only the meaning does."""
    return SequenceMatcher(None, _normalize(a), _normalize(b)).ratio()


def semantic_similarity(a, b):
    """Cosine similarity of the two answers' embeddings (nomic-embed-text).
    Returns None if embedding fails so the caller can fall back to the
    string score rather than silently scoring 0."""
    try:
        va = embed_text(a or "")
        vb = embed_text(b or "")
    except Exception:
        return None
    return _cosine(va, vb)


def score_answer(final_answer, ground_truth, threshold=DEFAULT_THRESHOLD):
    """Returns a dict with both similarity scores and a correct/incorrect
    verdict. Correctness is decided on the semantic score when available
    (meaning matters more than exact wording for QA), falling back to the
    string score if embeddings are unavailable."""
    sem = semantic_similarity(final_answer, ground_truth)
    stri = string_similarity(final_answer, ground_truth)

    basis = sem if sem is not None else stri
    correct = basis >= threshold

    return {
        "semantic_similarity": round(sem, 4) if sem is not None else None,
        "string_similarity": round(stri, 4),
        "threshold": threshold,
        "correct": correct,
        "correctness_basis": "semantic" if sem is not None else "string",
    }
```

## 50. `backend/experiments/warmup.py`

*22 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

"""Warm up the local models before timing, so the first real question isn't
penalised by Ollama loading a multi-GB model into memory (cold start). Timing
that would skew the latency numbers a research paper reports."""

from rag_agent.embedder import embed_text
from router_agent.llm_client import classify_question


def warm_up_models():
    errors = []
    try:
        embed_text("warmup")
    except Exception as exc:
        errors.append(f"embedding warmup failed: {exc}")
    try:
        # Any chat call loads qwen2.5:7b; the router prompt is the cheapest.
        classify_question("warmup")
    except Exception as exc:
        errors.append(f"llm warmup failed: {exc}")
    return errors
```

## 51. `backend/health/__init__.py`

*1 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.
```

## 52. `backend/health/apps.py`

*8 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

from django.apps import AppConfig


class HealthConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "health"
```

## 53. `backend/health/management/__init__.py`

*1 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.
```

## 54. `backend/health/management/commands/__init__.py`

*1 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.
```

## 55. `backend/health/management/commands/check_rag_agent_ro.py`

*121 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

import os

import psycopg2
from django.core.management.base import BaseCommand, CommandError

WRITE_PRIVILEGES = ["INSERT", "UPDATE", "DELETE", "TRUNCATE"]


class Command(BaseCommand):
    help = (
        "Connects to Postgres as the read-only rag_agent_ro role (NOT the app's "
        "own DB user) and prints every table it can see, plus which privileges "
        "it actually holds on each — to verify the read-only lockdown from "
        "db/sql/create_rag_agent_ro.sql took effect."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--check-write",
            action="store_true",
            help=(
                "Additionally attempt a real INSERT (inside a transaction that "
                "is always rolled back) against the first visible table, to "
                "prove writes are rejected by Postgres itself, not just absent "
                "from the catalog. Off by default since it burns a sequence "
                "value even on rollback."
            ),
        )

    def handle(self, *args, **options):
        password = os.getenv("RAG_AGENT_RO_PASSWORD")
        if not password:
            raise CommandError(
                "RAG_AGENT_RO_PASSWORD is not set. Add it to .env (matching the "
                "password used in db/sql/create_rag_agent_ro.sql) before running "
                "this command."
            )

        conn = psycopg2.connect(
            host=os.getenv("RAG_AGENT_RO_HOST", os.getenv("POSTGRES_HOST", "postgres")),
            port=os.getenv("RAG_AGENT_RO_PORT", os.getenv("POSTGRES_PORT", "5432")),
            dbname=os.getenv("RAG_AGENT_RO_DB", os.getenv("POSTGRES_DB", "college_rag")),
            user=os.getenv("RAG_AGENT_RO_USER", "rag_agent_ro"),
            password=password,
        )
        conn.autocommit = True

        try:
            with conn.cursor() as cur:
                cur.execute("SELECT current_user, session_user;")
                current_user, session_user = cur.fetchone()
                self.stdout.write(f"Connected as: {current_user} (session_user={session_user})")

                cur.execute("SHOW default_transaction_read_only;")
                self.stdout.write(f"default_transaction_read_only: {cur.fetchone()[0]}")

                cur.execute(
                    """
                    SELECT table_schema, table_name
                    FROM information_schema.tables
                    WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
                    ORDER BY table_schema, table_name;
                    """
                )
                tables = cur.fetchall()

                if not tables:
                    self.stdout.write(self.style.WARNING("No tables visible to this user."))
                    return

                self.stdout.write(f"\nTables visible to {current_user}:")
                for schema, table in tables:
                    full_name = f"{schema}.{table}"
                    granted = []
                    for priv in ["SELECT", *WRITE_PRIVILEGES]:
                        cur.execute("SELECT has_table_privilege(%s, %s);", (full_name, priv))
                        if cur.fetchone()[0]:
                            granted.append(priv)

                    unexpected_writes = [p for p in granted if p in WRITE_PRIVILEGES]
                    status = self.style.ERROR("UNEXPECTED WRITE ACCESS") if unexpected_writes else self.style.SUCCESS("OK")
                    self.stdout.write(f"  {full_name:<40} privileges: {', '.join(granted) or 'none':<30} [{status}]")

                if options["check_write"]:
                    self._check_write(cur, tables[0])
        finally:
            conn.close()

    def _check_write(self, cur, first_table):
        schema, table = first_table
        full_name = f"{schema}.{table}"
        self.stdout.write(f"\nAttempting a real INSERT into {full_name} (will be rolled back)...")
        try:
            cur.execute("BEGIN;")
            cur.execute(f"INSERT INTO {full_name} DEFAULT VALUES;")
        except psycopg2.errors.InsufficientPrivilege:
            self.stdout.write(self.style.SUCCESS("INSERT correctly rejected: insufficient privilege."))
        except psycopg2.errors.ReadOnlySqlTransaction:
            self.stdout.write(
                self.style.SUCCESS(
                    "INSERT correctly rejected: session is read-only "
                    "(default_transaction_read_only blocked it before the "
                    "table-privilege check even ran)."
                )
            )
        except psycopg2.Error as exc:
            # Any other error (e.g. a NOT NULL column with no default) still
            # proves the statement wasn't blocked purely on privilege grounds,
            # which is inconclusive rather than a pass — surface it as such.
            self.stdout.write(
                self.style.WARNING(
                    f"INSERT failed for a different reason ({exc.__class__.__name__}): "
                    f"{exc}. Privilege check inconclusive for this table."
                )
            )
        else:
            self.stdout.write(self.style.ERROR("INSERT SUCCEEDED — read-only lockdown is NOT working!"))
        finally:
            cur.execute("ROLLBACK;")
```

## 56. `backend/health/urls.py`

*10 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

from django.urls import path

from .views import health_check, liveness

urlpatterns = [
    path("", health_check, name="health-check"),
    path("live/", liveness, name="health-live"),
]
```

## 57. `backend/health/views.py`

*62 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

import logging

from django.db import connections
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from common import ollama
from rag_agent import vector_store

logger = logging.getLogger("health")


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def liveness(request):
    """Cheap liveness probe for the container healthcheck: confirms only that
    the backend process is up and serving. Does NOT check dependencies, so a
    downstream outage (e.g. Ollama) never marks the backend itself unhealthy."""
    return Response({"status": "ok", "service": "backend"})


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def health_check(request):
    """Aggregate readiness check across every backing service, for monitoring.
    Returns 200 when all are up, 503 when any is down, plus a per-service
    breakdown so it's obvious which one failed."""
    services = {
        "database": _check_database(),
        "llm": _check_llm(),
        "vector_store": _check_vector_store(),
    }
    all_ok = all(services.values())
    body = {
        "status": "ok" if all_ok else "degraded",
        "services": {name: ("up" if ok else "down") for name, ok in services.items()},
    }
    return Response(body, status=200 if all_ok else 503)


def _check_database():
    try:
        with connections["default"].cursor() as cur:
            cur.execute("SELECT 1;")
            cur.fetchone()
        return True
    except Exception as exc:
        logger.warning("health: database check failed: %s", exc)
        return False


def _check_llm():
    return ollama.ping()


def _check_vector_store():
    return vector_store.ping()
```

## 58. `backend/manage.py`

*21 lines*

```python
#!/usr/bin/env python
# Copyright (c) 2026 Yash Garad. All rights reserved.
import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
```

## 59. `backend/orchestrator/__init__.py`

*1 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.
```

## 60. `backend/orchestrator/apps.py`

*8 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

from django.apps import AppConfig


class OrchestratorConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "orchestrator"
```

## 61. `backend/orchestrator/sanitize.py`

*58 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

import re

# Defense-in-depth for the chat box. The real structural guarantees are
# elsewhere — the SQL guard rejects anything touching non-allowlisted tables
# or attempting writes, and the RAG agent is read-only — so a prompt-injection
# attempt can't reach the database destructively. This layer caps abuse
# (huge prompts burning LLM compute) and neutralizes control characters that
# could forge fake lines in the audit log or agent logs.

MAX_QUESTION_LENGTH = 500

# Strip C0/C1 control characters except normal whitespace (tab/newline are
# collapsed to spaces below anyway). Prevents log-line forging and terminal
# escape tricks in anything that echoes the question.
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
_WHITESPACE = re.compile(r"\s+")

# Phrases we record (not block) — blocking on wording is brittle and easy to
# evade, so we surface them in the audit trail rather than reject, and let the
# structural defenses do the actual protecting.
_INJECTION_PATTERNS = [
    re.compile(r"ignore (all |the )?(previous|prior|above) (instructions|prompts)", re.I),
    re.compile(r"disregard (all |the )?(previous|prior|above)", re.I),
    re.compile(r"system prompt", re.I),
    re.compile(r"you are now", re.I),
    re.compile(r"drop\s+table", re.I),
    re.compile(r"delete\s+from", re.I),
]


class QuestionRejected(Exception):
    """Raised when input can't be made into a usable question. `code` is one of
    'empty' or 'too_long' so the caller can respond politely per case."""

    def __init__(self, message, code):
        super().__init__(message)
        self.code = code


def sanitize_question(raw):
    """Return (clean_text, flags). Raises QuestionRejected for empty or
    over-length input. `flags` lists any injection-style patterns seen — for
    the audit log, not for blocking."""
    text = _CONTROL_CHARS.sub("", str(raw or ""))
    text = _WHITESPACE.sub(" ", text).strip()

    if not text:
        raise QuestionRejected("the question is empty", code="empty")
    if len(text) > MAX_QUESTION_LENGTH:
        raise QuestionRejected(
            f"the question is too long ({len(text)} chars; max {MAX_QUESTION_LENGTH})",
            code="too_long",
        )

    flags = [p.pattern for p in _INJECTION_PATTERNS if p.search(text)]
    return text, flags
```

## 62. `backend/orchestrator/service.py`

*191 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

import logging
from concurrent.futures import ThreadPoolExecutor

from common.exceptions import (
    DatabaseUnavailable,
    ServiceUnavailable,
    VectorStoreUnavailable,
)
from rag_agent.service import retrieve
from router_agent.classifier import classify
from sql_agent.service import ask as sql_ask
from synthesis_agent.service import synthesize_answer, synthesize_answer_stream

logger = logging.getLogger("orchestrator")

DEFAULT_ROUTE_ON_ERROR = "BOTH"
RAG_TOP_K = 5

# User-facing degradation notes appended to an answer when one source is down
# but we could still answer from the other.
DB_DOWN_NOTE = (
    "Note: live records lookup is temporarily unavailable, so this answer is "
    "based on descriptive information only."
)
RAG_DOWN_NOTE = (
    "Note: descriptive search is temporarily unavailable, so this answer is "
    "based on the structured records only."
)
RAG_DOWN_SQL_FALLBACK_NOTE = (
    "Note: descriptive search is temporarily unavailable; answering from the "
    "structured records instead."
)


def _resolve_route(question):
    # classify() can raise LLMUnavailable (Ollama down) — we let that propagate,
    # since if the LLM is down synthesis can't run either. A *parse* failure
    # (route_result.error) is different: fall back to BOTH and carry on.
    route_result = classify(question)
    if route_result.error:
        logger.warning(
            "router failed question=%r error=%s — falling back to %s",
            question, route_result.error, DEFAULT_ROUTE_ON_ERROR,
        )
        return DEFAULT_ROUTE_ON_ERROR, f"router error, defaulted to {DEFAULT_ROUTE_ON_ERROR}"
    return route_result.route, route_result.reason


def _run_sql(question):
    return sql_ask(question, execute=True)


def _run_rag(question):
    return retrieve(question, top_k=RAG_TOP_K)


def _gather_sources(question, route):
    """Fetch SQL and/or RAG data for the route, degrading gracefully when ONE
    source is down. Returns (sql_result, rag_chunks, effective_route, notes).

    Raises a ServiceUnavailable only when no usable source remains (e.g. a
    SQL-only question with the database down, or a descriptive question with
    the vector store down and no useful SQL fallback). LLMUnavailable from the
    embed/generate steps propagates untouched — if the LLM is down, the whole
    request can't be served anyway.
    """
    needs_sql = route in ("SQL", "BOTH")
    needs_rag = route in ("RAG", "BOTH")
    sql_result = None
    rag_chunks = None
    notes = []

    if needs_sql and needs_rag:
        # Independent I/O — run concurrently, but tolerate either one failing.
        with ThreadPoolExecutor(max_workers=2) as pool:
            f_sql = pool.submit(_run_sql, question)
            f_rag = pool.submit(_run_rag, question)
            try:
                sql_result = f_sql.result()
            except DatabaseUnavailable as exc:
                logger.warning("SQL source down (route=BOTH), degrading to RAG-only: %s", exc)
                notes.append(DB_DOWN_NOTE)
            try:
                rag_chunks = f_rag.result()
            except VectorStoreUnavailable as exc:
                logger.warning("RAG source down (route=BOTH), degrading to SQL-only: %s", exc)
                notes.append(RAG_DOWN_NOTE)

        if sql_result is None and rag_chunks is None:
            raise ServiceUnavailable()  # both sources down — nothing to answer from
        effective = "BOTH"
        if sql_result is not None and rag_chunks is None:
            effective = "SQL"
        elif rag_chunks is not None and sql_result is None:
            effective = "RAG"
        return sql_result, rag_chunks, effective, notes

    if needs_sql:  # SQL-only — a DB outage here is fatal (no source to fall back on)
        sql_result = _run_sql(question)
        return sql_result, None, "SQL", notes

    # RAG-only
    try:
        rag_chunks = _run_rag(question)
    except VectorStoreUnavailable:
        # Try SQL as a fallback; use it only if it actually found something.
        logger.warning("RAG source down (route=RAG), attempting SQL fallback")
        fallback = _run_sql(question)
        if fallback.rows:
            notes.append(RAG_DOWN_SQL_FALLBACK_NOTE)
            return fallback, None, "SQL", notes
        raise  # nothing useful from SQL — surface the clean "descriptive search down" message
    return None, rag_chunks, "RAG", notes


def answer_question(question):
    """Full pipeline, blocking. Returns a dict with the final answer plus
    intermediate metadata. Degrades gracefully; raises ServiceUnavailable only
    when nothing can be answered."""
    route, reason = _resolve_route(question)
    sql_result, rag_chunks, effective_route, notes = _gather_sources(question, route)
    answer = synthesize_answer(question, effective_route, sql_result=sql_result, rag_chunks=rag_chunks)
    if notes:
        answer = answer + "\n\n" + "\n".join(notes)

    logger.info("answered question=%r route=%s degraded=%s", question, effective_route, bool(notes))
    return {
        "question": question,
        "route": effective_route,
        "route_reason": reason,
        "answer": answer,
        "degraded": bool(notes),
        "notes": notes,
        "sql": _sql_meta(sql_result),
        "rag": _rag_meta(rag_chunks),
    }


def answer_question_stream(question):
    """Full pipeline, streaming. Yields ('meta', {...}), then ('token', str)
    per piece, then ('done', {...}). Degradation notes (if any) are streamed
    as trailing tokens so the user sees why the answer is limited. Raises
    ServiceUnavailable when nothing can be answered — the API layer turns that
    into a clean user-facing message."""
    route, reason = _resolve_route(question)
    sql_result, rag_chunks, effective_route, notes = _gather_sources(question, route)

    yield "meta", {
        "question": question,
        "route": effective_route,
        "route_reason": reason,
        "degraded": bool(notes),
        "sql": _sql_meta(sql_result),
        "rag": _rag_meta(rag_chunks),
    }

    pieces = []
    for piece in synthesize_answer_stream(
        question, effective_route, sql_result=sql_result, rag_chunks=rag_chunks
    ):
        pieces.append(piece)
        yield "token", piece

    for note in notes:
        note_text = "\n\n" + note
        pieces.append(note_text)
        yield "token", note_text

    logger.info("streamed answer question=%r route=%s degraded=%s", question, effective_route, bool(notes))
    yield "done", {"answer": "".join(pieces)}


def _sql_meta(sql_result):
    if sql_result is None:
        return None
    return {
        "generated_sql": sql_result.generated_sql,
        "error": sql_result.error,
        "row_count": len(sql_result.rows) if sql_result.rows else 0,
    }


def _rag_meta(rag_chunks):
    if not rag_chunks:
        return None
    return [
        {"table": c.table, "row_id": c.row_id, "score": round(c.score, 4)}
        for c in rag_chunks
    ]
```

## 63. `backend/orchestrator/urls.py`

*9 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

from django.urls import path

from .views import ask

urlpatterns = [
    path("", ask, name="ask"),
]
```

## 64. `backend/orchestrator/views.py`

*142 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

import json
import logging
import time

from django.http import StreamingHttpResponse
from rest_framework.decorators import api_view, permission_classes, throttle_classes

from accounts.permissions import IsStaffUser
from accounts.throttling import AskRateThrottle
from audit.models import AuditLog
from common.exceptions import ServiceUnavailable

from .sanitize import QuestionRejected, sanitize_question
from .service import answer_question_stream

logger = logging.getLogger("orchestrator")

# Polite, non-technical replies for input problems — shown as a normal
# assistant message rather than an error, so the chat never "errors out".
POLITE_MESSAGES = {
    "empty": (
        "It looks like your message was empty. Please type a question about "
        "courses, departments, faculty, fees, or schedules."
    ),
    "too_long": (
        "That question is a bit long (the limit is 500 characters). Please "
        "shorten it and try again."
    ),
}
GENERIC_ERROR = "Something went wrong while answering. Please try again in a moment."


def _sse(event, data):
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _client_ip(request):
    # Behind the Caddy proxy the real client is the first X-Forwarded-For hop.
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


_AGENTS_FOR_ROUTE = {"SQL": "sql", "RAG": "rag", "BOTH": "sql+rag"}


@api_view(["POST"])
@permission_classes([IsStaffUser])
@throttle_classes([AskRateThrottle])
def ask(request):
    username = getattr(request.user, "username", "") or "anonymous"
    client_ip = _client_ip(request)
    raw_question = request.data.get("question")

    try:
        question, injection_flags = sanitize_question(raw_question)
    except QuestionRejected as exc:
        # Respond politely (as a normal assistant reply) instead of erroring out.
        message = POLITE_MESSAGES.get(exc.code, POLITE_MESSAGES["empty"])
        _write_audit(
            username=username, client_ip=client_ip,
            question=(str(raw_question or "")[:500]), meta={},
            answer=message, injection_flags=[], latency_ms=0.0,
        )
        return _sse_stream(_polite_events(message))

    started = time.perf_counter()

    def event_stream():
        meta = {}
        answer_parts = []
        final_answer = None
        try:
            for kind, payload in answer_question_stream(question):
                if kind == "meta":
                    meta = payload
                elif kind == "token":
                    answer_parts.append(payload)
                    yield _sse("token", {"text": payload})
                    continue
                elif kind == "done":
                    final_answer = payload.get("answer", "".join(answer_parts))
                yield _sse(kind, payload)
        except ServiceUnavailable as exc:
            # A backing service is down — show the safe user_message, never the
            # raw connection error. The technical detail is logged below.
            logger.warning("service unavailable for question=%r: %s", question, exc)
            final_answer = exc.user_message
            yield _sse("error", {"error": exc.user_message})
        except Exception:
            logger.exception("unexpected error answering question=%r", question)
            final_answer = GENERIC_ERROR
            yield _sse("error", {"error": GENERIC_ERROR})
        finally:
            _write_audit(
                username=username,
                client_ip=client_ip,
                question=question,
                meta=meta,
                answer=final_answer if final_answer is not None else "".join(answer_parts),
                injection_flags=injection_flags,
                latency_ms=round((time.perf_counter() - started) * 1000, 1),
            )

    return _sse_stream(event_stream())


def _polite_events(message):
    # A minimal SSE stream that delivers a single assistant message.
    yield _sse("meta", {"route": None, "degraded": False})
    yield _sse("token", {"text": message})
    yield _sse("done", {"answer": message})


def _sse_stream(generator):
    response = StreamingHttpResponse(generator, content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"  # disable proxy buffering so tokens flush immediately
    return response


def _write_audit(*, username, client_ip, question, meta, answer, injection_flags, latency_ms):
    # Never let an audit-write failure break the user's answer — log and move on.
    try:
        route = meta.get("route") or "" if meta else ""
        sql_meta = (meta or {}).get("sql") or {}
        AuditLog.objects.create(
            username=username,
            client_ip=client_ip,
            question=question,
            route=route,
            agents_used=_AGENTS_FOR_ROUTE.get(route, ""),
            generated_sql=sql_meta.get("generated_sql"),
            final_answer=answer,
            injection_flags=", ".join(injection_flags),
            latency_ms=latency_ms,
        )
    except Exception:
        logger.exception("failed to write audit log for question=%r", question)
```

## 65. `backend/rag_agent/__init__.py`

*1 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.
```

## 66. `backend/rag_agent/apps.py`

*8 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

from django.apps import AppConfig


class RagAgentConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "rag_agent"
```

## 67. `backend/rag_agent/embedder.py`

*21 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

import os

from common import ollama

# Same model/config sync_worker embeds rows with — a query embedded with a
# different model would land in a different vector space and every
# similarity score would be meaningless.
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "768"))


def embed_text(text):
    # Raises common.exceptions.LLMUnavailable if Ollama is down/slow.
    embedding = ollama.embeddings(EMBEDDING_MODEL, text)
    if len(embedding) != EMBEDDING_DIM:
        raise ValueError(
            f"expected a {EMBEDDING_DIM}-dim embedding from {EMBEDDING_MODEL}, got {len(embedding)}"
        )
    return embedding
```

## 68. `backend/rag_agent/management/__init__.py`

*1 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.
```

## 69. `backend/rag_agent/management/commands/__init__.py`

*1 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.
```

## 70. `backend/rag_agent/management/commands/demo_rag_agent.py`

*41 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

from django.core.management.base import BaseCommand

from rag_agent.service import retrieve

TEST_QUESTIONS = [
    "Tell me about the Computer Science department.",
    "What is the Mathematics department about?",
    "Which course covers neural networks and machine learning?",
    "I want to study Shakespeare's plays — which course should I take?",
    "What course teaches me about financial statements and accounting?",
]


class Command(BaseCommand):
    help = (
        "Runs 5 sample questions through the RAG retrieval agent (embed with "
        "nomic-embed-text, search Qdrant, top-k with source metadata) and "
        "prints the retrieved chunks so relevance can be checked by eye."
    )

    def add_arguments(self, parser):
        parser.add_argument("--top-k", type=int, default=5)

    def handle(self, *args, **options):
        top_k = options["top_k"]

        for i, question in enumerate(TEST_QUESTIONS, 1):
            self.stdout.write(self.style.MIGRATE_HEADING(f"\n[{i}] Q: {question}"))
            chunks = retrieve(question, top_k=top_k)

            if not chunks:
                self.stdout.write(self.style.WARNING("    (no results — is the college_docs collection empty?)"))
                continue

            for rank, chunk in enumerate(chunks, 1):
                self.stdout.write(
                    f"    #{rank}  score={chunk.score:.4f}  "
                    f"[{chunk.table}#{chunk.row_id}]  {chunk.text}"
                )
```

## 71. `backend/rag_agent/service.py`

*47 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

import logging

from . import embedder, vector_store

logger = logging.getLogger("rag_agent")


class RetrievedChunk:
    def __init__(self, table, row_id, last_updated, text, score):
        self.table = table
        self.row_id = row_id
        self.last_updated = last_updated
        self.text = text
        self.score = score

    def to_dict(self):
        return {
            "table": self.table,
            "row_id": self.row_id,
            "last_updated": self.last_updated,
            "text": self.text,
            "score": self.score,
        }


def retrieve(question, top_k=5):
    vector = embedder.embed_text(question)
    points = vector_store.search(vector, limit=top_k)

    chunks = [
        RetrievedChunk(
            table=p.payload.get("table"),
            row_id=p.payload.get("row_id"),
            last_updated=p.payload.get("last_updated"),
            text=p.payload.get("text"),
            score=p.score,
        )
        for p in points
    ]

    logger.info(
        "question=%r retrieved=%d chunks top_score=%s",
        question, len(chunks), f"{chunks[0].score:.4f}" if chunks else None,
    )
    return chunks
```

## 72. `backend/rag_agent/vector_store.py`

*52 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

import os

from qdrant_client import QdrantClient

from common.exceptions import VectorStoreUnavailable

QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "college_docs")
# Bound how long we wait on Qdrant so an unreachable vector store fails fast.
QDRANT_TIMEOUT_S = float(os.getenv("QDRANT_TIMEOUT", "5"))

_client = None


def get_client():
    global _client
    if _client is None:
        _client = QdrantClient(url=QDRANT_URL, timeout=QDRANT_TIMEOUT_S)
    return _client


def search(query_vector, limit=5):
    # No table filter needed: college_docs only ever contains points from
    # the descriptive tables (departments/faculty/programs/courses) — that's
    # enforced upstream by sync_worker only embedding those (see
    # sync_worker/config.py DESCRIPTIVE_TABLES), not by anything here.
    #
    # Raises VectorStoreUnavailable if Qdrant is unreachable, so callers can
    # fall back to SQL-only or tell the user descriptive search is down.
    try:
        response = get_client().query_points(
            collection_name=QDRANT_COLLECTION,
            query=query_vector,
            limit=limit,
        )
    except Exception as exc:
        raise VectorStoreUnavailable(f"Qdrant search failed: {exc}") from exc
    return response.points


def ping(timeout=3):
    """Lightweight liveness probe for the health endpoint. Returns True if
    Qdrant responds, False otherwise (never raises). Uses a short-lived client
    with its own timeout so a hung Qdrant doesn't stall the health check."""
    try:
        client = QdrantClient(url=QDRANT_URL, timeout=timeout)
        client.get_collections()
        return True
    except Exception:
        return False
```

## 73. `backend/requirements.txt`

*11 lines*

```text
# Copyright (c) 2026 Yash Garad. All rights reserved.

Django>=5.0,<6.0
djangorestframework>=3.15
psycopg2-binary>=2.9
django-cors-headers>=4.4
python-dotenv>=1.0
gunicorn>=22.0
sqlglot>=25.0
qdrant-client>=1.9
requests>=2.32
```

## 74. `backend/router_agent/__init__.py`

*1 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.
```

## 75. `backend/router_agent/apps.py`

*8 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

from django.apps import AppConfig


class RouterAgentConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "router_agent"
```

## 76. `backend/router_agent/classifier.py`

*49 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

import json
import logging
import re

from . import llm_client

logger = logging.getLogger("router_agent")

VALID_ROUTES = {"SQL", "RAG", "BOTH"}

_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


class RouteResult:
    def __init__(self, question, route=None, reason=None, raw_output=None, error=None):
        self.question = question
        self.route = route
        self.reason = reason
        self.raw_output = raw_output
        self.error = error

    @property
    def ok(self):
        return self.error is None


def classify(question):
    """Classifies a question as SQL / RAG / BOTH. Does not call either agent
    — this is routing decision-making only, kept deliberately separate so it
    can be reviewed on its own before anything gets wired to it."""
    raw_output = llm_client.classify_question(question)
    text = _CODE_FENCE_RE.sub("", raw_output).strip()

    try:
        parsed = json.loads(text)
        route = str(parsed.get("route", "")).strip().upper()
        reason = parsed.get("reason", "")
    except (json.JSONDecodeError, AttributeError) as exc:
        logger.warning("failed to parse router output question=%r raw=%r error=%s", question, raw_output, exc)
        return RouteResult(question, raw_output=raw_output, error=f"could not parse model output as JSON: {exc}")

    if route not in VALID_ROUTES:
        logger.warning("router returned invalid route question=%r route=%r raw=%r", question, route, raw_output)
        return RouteResult(question, raw_output=raw_output, error=f"model returned invalid route: {route!r}")

    logger.info("question=%r route=%s reason=%s", question, route, reason)
    return RouteResult(question, route=route, reason=reason, raw_output=raw_output)
```

## 77. `backend/router_agent/llm_client.py`

*56 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

import os

from common import ollama

# LLM_MODEL is the single knob for the model all agents use; ROUTER_MODEL is
# an optional per-agent override that defaults to it.
ROUTER_MODEL = os.getenv("ROUTER_MODEL", os.getenv("LLM_MODEL", "qwen2.5:7b"))

SYSTEM_PROMPT = """You are a router that decides which backend should handle a user's question about a college information system.

There are two backends:
- SQL: a text-to-SQL agent that queries structured data directly. Use it for precise facts, counts, lists, filters, joins, numeric values, schedules, fees, or specific record lookups — anything with a single well-defined answer pulled from a table.
- RAG: a semantic search agent over descriptive text (department, faculty, program, and course descriptions). Use it for open-ended, "tell me about", "what does X cover", conceptual, or descriptive questions where there's no single precise field to look up.

Some questions genuinely need BOTH — they ask for a specific structured fact AND an open-ended description in the same question.

Given a question, respond with ONLY a JSON object of the form:
{"route": "SQL" | "RAG" | "BOTH", "reason": "<one short sentence explaining why>"}

No markdown, no extra text — just that JSON object.

Examples:

Q: How many faculty members are in the Computer Science department?
A: {"route": "SQL", "reason": "Asks for a count, a precise structured aggregate."}

Q: What does the Machine Learning Fundamentals course cover?
A: {"route": "RAG", "reason": "Open-ended request for descriptive course content."}

Q: List all programs that take longer than 3 years to complete.
A: {"route": "SQL", "reason": "A filtered list pulled from structured program data."}

Q: Tell me about the Mathematics department.
A: {"route": "RAG", "reason": "General descriptive question with no single precise field to look up."}

Q: What is the tuition fee for the Computer Science program, and can you describe what the program covers?
A: {"route": "BOTH", "reason": "Asks for a precise fee (SQL) and a descriptive summary (RAG) in one question."}

Q: When is the exam for course CS310?
A: {"route": "SQL", "reason": "A precise scheduled fact lookup."}
"""


def classify_question(question):
    # Raises common.exceptions.LLMUnavailable if Ollama is down/slow.
    return ollama.chat(
        ROUTER_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ],
        options={"temperature": 0},
        response_format="json",
    )
```

## 78. `backend/router_agent/management/__init__.py`

*1 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.
```

## 79. `backend/router_agent/management/commands/__init__.py`

*1 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.
```

## 80. `backend/router_agent/management/commands/demo_router_agent.py`

*53 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

from django.core.management.base import BaseCommand

from router_agent.classifier import classify

# Mix of clear SQL lookups, clear RAG/descriptive questions, and a few that
# genuinely need both, to exercise all three routes before wiring this into
# anything else.
TEST_QUESTIONS = [
    "How many faculty members work in the Computer Science department?",
    "What does the Organic Chemistry course cover?",
    "List all programs offered by the Mathematics department.",
    "Tell me about the Computer Science department.",
    "What is the tuition fee for the Computer Science program?",
    "When is the exam scheduled for course CS310?",
    "I'm interested in studying literature — what courses would you recommend and when are they scheduled?",
    "What is the Machine Learning Fundamentals course about, and how many credits is it worth?",
    "Which department was established in 1970?",
    "Describe the Financial Accounting course and tell me its exam date.",
]


class Command(BaseCommand):
    help = (
        "Classifies 10 mixed test questions as SQL / RAG / BOTH using the "
        "router agent and prints each classification + reasoning for "
        "review. This is classification only — it does not call the SQL "
        "or RAG agents themselves."
    )

    def handle(self, *args, **options):
        counts = {"SQL": 0, "RAG": 0, "BOTH": 0, "ERROR": 0}

        for i, question in enumerate(TEST_QUESTIONS, 1):
            result = classify(question)
            self.stdout.write(self.style.MIGRATE_HEADING(f"[{i}] Q: {question}"))

            if result.error:
                counts["ERROR"] += 1
                self.stdout.write(self.style.ERROR(f"    ERROR: {result.error}"))
                if result.raw_output:
                    self.stdout.write(f"    raw output: {result.raw_output!r}")
            else:
                counts[result.route] += 1
                self.stdout.write(f"    ROUTE: {result.route}  —  {result.reason}")

            self.stdout.write("")

        self.stdout.write(self.style.MIGRATE_HEADING("Summary:"))
        self.stdout.write(
            f"  SQL={counts['SQL']}  RAG={counts['RAG']}  BOTH={counts['BOTH']}  ERROR={counts['ERROR']}"
        )
```

## 81. `backend/sql_agent/__init__.py`

*1 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.
```

## 82. `backend/sql_agent/apps.py`

*8 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

from django.apps import AppConfig


class SqlAgentConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "sql_agent"
```

## 83. `backend/sql_agent/db.py`

*15 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

import os

# Deliberately NOT Django's own DB connection (that's the app-owner user).
# The SQL agent — both for schema introspection and for running
# LLM-generated queries — only ever connects as rag_agent_ro, so a bug here
# can't do more than that role's grants allow (see db/sql/create_rag_agent_ro.sql).
RAG_AGENT_RO_CONFIG = {
    "host": os.getenv("RAG_AGENT_RO_HOST", os.getenv("POSTGRES_HOST", "postgres")),
    "port": os.getenv("RAG_AGENT_RO_PORT", os.getenv("POSTGRES_PORT", "5432")),
    "dbname": os.getenv("RAG_AGENT_RO_DB", os.getenv("POSTGRES_DB", "college_rag")),
    "user": os.getenv("RAG_AGENT_RO_USER", "rag_agent_ro"),
    "password": os.getenv("RAG_AGENT_RO_PASSWORD"),
}
```

## 84. `backend/sql_agent/executor.py`

*49 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

import psycopg2
import psycopg2.extras

from common.exceptions import DatabaseUnavailable

from . import db

# Extra defense-in-depth beyond the role-level grants and
# default_transaction_read_only: even a legitimate SELECT shouldn't be
# allowed to hang the connection indefinitely.
STATEMENT_TIMEOUT_MS = 5000

# Bound how long we wait to establish a connection so a DOWN database fails
# fast instead of hanging the request.
CONNECT_TIMEOUT_S = 5


def run_query(sql):
    """Runs an already-validated, already-capped SELECT as rag_agent_ro.
    Never call this with unvalidated SQL — guard.validate_and_cap() is what
    makes this safe to call at all.

    Raises DatabaseUnavailable if the database is unreachable or the
    connection drops mid-query. That exception carries a user-safe message;
    the raw psycopg2 error stays in the logs.
    """
    try:
        conn = psycopg2.connect(connect_timeout=CONNECT_TIMEOUT_S, **db.RAG_AGENT_RO_CONFIG)
    except psycopg2.OperationalError as exc:
        raise DatabaseUnavailable(f"could not connect to database: {exc}") from exc

    try:
        conn.autocommit = True
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(f"SET statement_timeout = {STATEMENT_TIMEOUT_MS};")
            cur.execute(sql)
            rows = [dict(row) for row in cur.fetchall()]
            columns = [desc[0] for desc in cur.description] if cur.description else []
        return columns, rows
    except psycopg2.OperationalError as exc:
        # Connection dropped mid-query (server restarted, network blip, etc.).
        raise DatabaseUnavailable(f"database connection lost mid-query: {exc}") from exc
    finally:
        try:
            conn.close()
        except Exception:
            pass
```

## 85. `backend/sql_agent/guard.py`

*91 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

import re

import sqlglot
from sqlglot import exp
from sqlglot.tokens import Tokenizer, TokenType

DIALECT = "postgres"
MAX_LIMIT = 50  # hard cap — not env-configurable on purpose, see README note in service.py

# The literal 5 keywords called out as a hard requirement. Enforced twice:
# structurally below (sqlglot's statement-type check already rules these
# out via the isinstance(stmt, exp.Select) check), and again here as a
# token-level net in case a future parser edge case ever lets one slip
# through. Checking *token type* rather than raw text/regex matters: a
# course literally titled "Update Systems" tokenizes UPDATE as a plain
# STRING, not a TokenType.UPDATE keyword, so it won't false-positive here
# the way a naive `\bUPDATE\b` regex over the raw SQL text would.
_HARD_FORBIDDEN_TOKEN_TYPES = {
    TokenType.INSERT,
    TokenType.UPDATE,
    TokenType.DELETE,
    TokenType.DROP,
    TokenType.ALTER,
}

_CODE_FENCE_RE = re.compile(r"^```(?:sql)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


class SqlRejected(Exception):
    pass


def _strip_code_fences(text):
    return _CODE_FENCE_RE.sub("", text).strip()


def validate_and_cap(raw_model_output, allowed_tables, max_limit=MAX_LIMIT):
    """Turns raw LLM output into a safe-to-run SQL string, or raises
    SqlRejected. Never returns anything but a single capped SELECT."""
    text = _strip_code_fences(raw_model_output).rstrip(";").strip()

    if not text or text.upper() == "NO_QUERY":
        raise SqlRejected("the model reported it could not answer this question with the given schema")

    try:
        statements = [s for s in sqlglot.parse(text, read=DIALECT) if s is not None]
    except Exception as exc:
        raise SqlRejected(f"generated SQL failed to parse: {exc}") from None

    if len(statements) != 1:
        raise SqlRejected(
            f"expected exactly one SQL statement, got {len(statements)} "
            "(stacked/multiple statements are not allowed)"
        )

    stmt = statements[0]

    if not isinstance(stmt, exp.Select):
        raise SqlRejected(f"only SELECT statements are allowed, got {type(stmt).__name__}")

    hit_types = {tok.token_type for tok in Tokenizer().tokenize(text)} & _HARD_FORBIDDEN_TOKEN_TYPES
    if hit_types:
        raise SqlRejected(f"query contains forbidden keyword(s): {', '.join(t.name for t in hit_types)}")

    referenced_tables = {t.name.lower() for t in stmt.find_all(exp.Table) if t.name}
    allowed_lower = {t.lower() for t in allowed_tables}
    disallowed = referenced_tables - allowed_lower
    if disallowed:
        raise SqlRejected(
            f"query references table(s) outside the allowed schema: {', '.join(sorted(disallowed))}"
        )

    return _cap_limit(stmt, max_limit).sql(dialect=DIALECT)


def _cap_limit(stmt, max_limit):
    stmt = stmt.copy()
    stmt.set("offset", None)  # pagination isn't supported by this agent

    existing_limit_node = stmt.args.get("limit")
    existing_value = None
    if existing_limit_node is not None:
        try:
            existing_value = int(existing_limit_node.expression.this)
        except (AttributeError, TypeError, ValueError):
            existing_value = None

    final_limit = min(existing_value, max_limit) if existing_value is not None else max_limit
    return stmt.limit(final_limit)
```

## 86. `backend/sql_agent/llm_client.py`

*36 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

import os

from common import ollama

# LLM_MODEL is the single knob for the model all agents use; SQL_AGENT_MODEL is
# an optional per-agent override that defaults to it.
SQL_AGENT_MODEL = os.getenv("SQL_AGENT_MODEL", os.getenv("LLM_MODEL", "qwen2.5:7b"))

SYSTEM_PROMPT_TEMPLATE = """You are a SQL generator for a read-only PostgreSQL database serving a college information system.

Given a natural language question, output EXACTLY ONE SQL SELECT statement (PostgreSQL dialect) that answers it — nothing else. No explanation, no markdown code fences, no comments. Just the raw SQL statement, ending in a semicolon.

Rules:
- Only SELECT statements. Never INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE, CREATE, GRANT, or any other data-modifying or schema-modifying statement.
- Only reference tables and columns from the schema below. Never invent a table or column that isn't listed.
- Do not add your own LIMIT clause — the system enforces one automatically.
- If the question cannot be answered using only the schema below, respond with exactly: NO_QUERY

Schema:
{schema}
"""


def generate_sql(question, schema_text):
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(schema=schema_text)
    # Raises common.exceptions.LLMUnavailable if Ollama is down/slow.
    return ollama.chat(
        SQL_AGENT_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ],
        options={"temperature": 0},
    )
```

## 87. `backend/sql_agent/management/__init__.py`

*1 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.
```

## 88. `backend/sql_agent/management/commands/__init__.py`

*1 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.
```

## 89. `backend/sql_agent/management/commands/demo_sql_agent.py`

*57 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

from django.core.management.base import BaseCommand

from sql_agent.service import ask

TEST_QUESTIONS = [
    "What courses does the Computer Science department offer?",
    "Which faculty members work in the Mathematics department?",
    "List all programs that take longer than 3 years to complete.",
    "What is the tuition fee for the Computer Science program?",
    "Show me the exam schedule for course CS310.",
]


class Command(BaseCommand):
    help = (
        "Runs 5 canned test questions through the SQL agent and prints the "
        "generated SQL for review. By default this ONLY generates and "
        "validates the SQL — it does not touch the database. Pass --execute "
        "to actually run the queries against rag_agent_ro and print results."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--execute",
            action="store_true",
            help="Also execute each generated query (as rag_agent_ro) and print the results.",
        )

    def handle(self, *args, **options):
        execute = options["execute"]
        mode = "GENERATE + EXECUTE" if execute else "GENERATE ONLY (dry run, no DB writes/reads of result data)"
        self.stdout.write(self.style.MIGRATE_HEADING(f"Mode: {mode}\n"))

        for i, question in enumerate(TEST_QUESTIONS, 1):
            self.stdout.write(self.style.MIGRATE_HEADING(f"[{i}] Q: {question}"))
            result = ask(question, execute=execute)

            if result.error:
                self.stdout.write(self.style.ERROR(f"    REJECTED/ERROR: {result.error}"))
                if result.raw_llm_output:
                    self.stdout.write(f"    raw model output: {result.raw_llm_output!r}")
                self.stdout.write("")
                continue

            self.stdout.write(f"    SQL: {result.generated_sql}")

            if execute:
                self.stdout.write(f"    columns: {result.columns}")
                self.stdout.write(f"    row count: {len(result.rows)}")
                for row in result.rows[:5]:
                    self.stdout.write(f"      {row}")
                if len(result.rows) > 5:
                    self.stdout.write(f"      ... ({len(result.rows) - 5} more)")

            self.stdout.write("")
```

## 90. `backend/sql_agent/schema.py`

*70 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

# Same table whitelist rag_agent_ro is granted SELECT on (see
# db/sql/create_rag_agent_ro.sql / sync_worker/config.py) — the agent can
# only ever see and query general institutional data, never the per-student
# tables (students, enrollments, attendance, exam_results, fee_payments).
ALLOWED_TABLES = [
    "departments",
    "faculty",
    "programs",
    "courses",
    "courses_prerequisites",
    "course_offerings",
    "rooms",
    "class_schedule",
    "exam_timetable",
    "fee_structure",
]

_COLUMNS_SQL = """
    SELECT table_name, column_name, data_type
    FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = ANY(%s)
    ORDER BY table_name, ordinal_position;
"""

_FK_SQL = """
    SELECT
        tc.table_name AS from_table,
        kcu.column_name AS from_column,
        ccu.table_name AS to_table,
        ccu.column_name AS to_column
    FROM information_schema.table_constraints tc
    JOIN information_schema.key_column_usage kcu
        ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
    JOIN information_schema.constraint_column_usage ccu
        ON tc.constraint_name = ccu.constraint_name AND tc.table_schema = ccu.table_schema
    WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'public'
      AND tc.table_name = ANY(%s);
"""


def build_schema_text(conn):
    """Introspects the live DB (as rag_agent_ro) for the whitelisted tables,
    so the prompt always reflects what the agent is actually allowed to
    query — it can never drift from db/sql/create_rag_agent_ro.sql."""
    with conn.cursor() as cur:
        cur.execute(_COLUMNS_SQL, (ALLOWED_TABLES,))
        columns_by_table = {}
        for table_name, column_name, data_type in cur.fetchall():
            columns_by_table.setdefault(table_name, []).append((column_name, data_type))

        cur.execute(_FK_SQL, (ALLOWED_TABLES,))
        foreign_keys = {}
        for from_table, from_column, to_table, to_column in cur.fetchall():
            foreign_keys[(from_table, from_column)] = (to_table, to_column)

    lines = []
    for table in ALLOWED_TABLES:
        if table not in columns_by_table:
            continue
        lines.append(f"TABLE {table} (")
        for column_name, data_type in columns_by_table[table]:
            fk = foreign_keys.get((table, column_name))
            suffix = f" REFERENCES {fk[0]}({fk[1]})" if fk else ""
            lines.append(f"  {column_name} {data_type}{suffix},")
        lines.append(")")
        lines.append("")

    return "\n".join(lines)
```

## 91. `backend/sql_agent/service.py`

*80 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

import logging

import psycopg2

from common.exceptions import DatabaseUnavailable

from . import db, executor, guard, llm_client, schema

logger = logging.getLogger("sql_agent")

CONNECT_TIMEOUT_S = 5


class SqlAgentResult:
    def __init__(self, question, raw_llm_output=None, generated_sql=None, columns=None, rows=None, error=None):
        self.question = question
        self.raw_llm_output = raw_llm_output
        self.generated_sql = generated_sql
        self.columns = columns
        self.rows = rows
        self.error = error

    @property
    def ok(self):
        return self.error is None


def ask(question, execute=True):
    """Natural language question -> validated+capped SQL -> (optionally) results.

    Every generated query is logged via the "sql_agent" logger *before* it's
    ever executed — including ones that get rejected — so there's always an
    audit trail of what the LLM produced, independent of whether it ran.
    """
    # Schema introspection connects to the DB; if it's unreachable, fail fast
    # with a user-safe DatabaseUnavailable rather than a raw psycopg2 trace.
    try:
        conn = psycopg2.connect(connect_timeout=CONNECT_TIMEOUT_S, **db.RAG_AGENT_RO_CONFIG)
    except psycopg2.OperationalError as exc:
        raise DatabaseUnavailable(f"could not connect to database: {exc}") from exc
    try:
        schema_text = schema.build_schema_text(conn)
    except psycopg2.OperationalError as exc:
        raise DatabaseUnavailable(f"database connection lost during schema read: {exc}") from exc
    finally:
        try:
            conn.close()
        except Exception:
            pass

    raw_output = llm_client.generate_sql(question, schema_text)

    try:
        capped_sql = guard.validate_and_cap(raw_output, schema.ALLOWED_TABLES)
    except guard.SqlRejected as exc:
        logger.warning("REJECTED question=%r raw_llm_output=%r reason=%s", question, raw_output, exc)
        return SqlAgentResult(question, raw_llm_output=raw_output, error=str(exc))

    logger.info("question=%r generated_sql=%s", question, capped_sql)

    if not execute:
        return SqlAgentResult(question, raw_llm_output=raw_output, generated_sql=capped_sql)

    try:
        columns, rows = executor.run_query(capped_sql)
    except DatabaseUnavailable:
        # Infrastructure failure — let the orchestrator decide how to degrade,
        # instead of burying a raw error string in the result.
        raise
    except Exception as exc:
        # A query-level error (e.g. Postgres rejects a valid-looking SELECT).
        # This is data-shaped, not infrastructure — record it and carry on.
        logger.exception("query execution failed question=%r sql=%s", question, capped_sql)
        return SqlAgentResult(question, raw_llm_output=raw_output, generated_sql=capped_sql, error=str(exc))

    return SqlAgentResult(
        question, raw_llm_output=raw_output, generated_sql=capped_sql, columns=columns, rows=rows
    )
```

## 92. `backend/sql_agent/tests.py`

*73 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

"""Regression tests for the SQL guard's table-access control.

These lock in the guarantee that the agent can only ever touch the allowlisted
tables — proven by rejection of a battery of evasion attempts. Pure unit tests:
no database or LLM needed (they call the guard directly).

Run with:  python manage.py test sql_agent
"""

from django.test import SimpleTestCase

from sql_agent import guard
from sql_agent.schema import ALLOWED_TABLES


class OutOfAllowlistRejectionTests(SimpleTestCase):
    # Each case is a query that tries to reach a table OUTSIDE the allowlist
    # (per-student data or system catalogs) through a different SQL construct.
    ATTACKS = {
        "per_student_table": "SELECT * FROM students",
        "schema_qualified": "SELECT * FROM public.students",
        "subquery": "SELECT code FROM courses WHERE credits > (SELECT count(*) FROM students)",
        "cte": "WITH x AS (SELECT * FROM enrollments) SELECT * FROM x",
        "union": "SELECT code FROM courses UNION SELECT roll_number FROM students",
        "join": "SELECT c.code FROM courses c JOIN exam_results e ON true",
        "information_schema": "SELECT table_name FROM information_schema.tables",
        "pg_catalog": "SELECT rolname FROM pg_catalog.pg_roles",
        "auth_table": "SELECT username, password FROM auth_user",
        "fee_payments": "SELECT * FROM fee_payments",
    }

    def test_all_out_of_allowlist_queries_are_rejected(self):
        for name, sql in self.ATTACKS.items():
            with self.subTest(attack=name):
                with self.assertRaises(guard.SqlRejected):
                    guard.validate_and_cap(sql, ALLOWED_TABLES)


class AllowlistedQueriesSucceedTests(SimpleTestCase):
    def test_plain_select_on_allowed_table_passes_and_is_capped(self):
        out = guard.validate_and_cap("SELECT code, title FROM courses", ALLOWED_TABLES)
        self.assertIn("LIMIT 50", out)

    def test_join_across_allowed_tables_passes(self):
        sql = (
            "SELECT c.code, d.name FROM courses c "
            "JOIN departments d ON c.department_id = d.id"
        )
        out = guard.validate_and_cap(sql, ALLOWED_TABLES)
        self.assertIn("LIMIT 50", out)


class WriteAndForbiddenKeywordTests(SimpleTestCase):
    def test_write_statements_rejected(self):
        for sql in (
            "UPDATE courses SET credits = 5",
            "DELETE FROM courses",
            "INSERT INTO courses (code) VALUES ('x')",
            "DROP TABLE courses",
            "SELECT 1; DROP TABLE courses;",
        ):
            with self.subTest(sql=sql):
                with self.assertRaises(guard.SqlRejected):
                    guard.validate_and_cap(sql, ALLOWED_TABLES)

    def test_keyword_in_string_literal_is_not_a_false_positive(self):
        # A course literally titled "Update Systems" must not trip the guard.
        out = guard.validate_and_cap(
            "SELECT * FROM courses WHERE title = 'Update Systems'", ALLOWED_TABLES
        )
        self.assertIn("LIMIT 50", out)
```

## 93. `backend/synthesis_agent/__init__.py`

*1 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.
```

## 94. `backend/synthesis_agent/apps.py`

*8 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

from django.apps import AppConfig


class SynthesisAgentConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "synthesis_agent"
```

## 95. `backend/synthesis_agent/llm_client.py`

*63 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

import os

from common import ollama

# LLM_MODEL is the single knob for the model all agents use; SYNTHESIS_MODEL is
# an optional per-agent override that defaults to it.
SYNTHESIS_MODEL = os.getenv("SYNTHESIS_MODEL", os.getenv("LLM_MODEL", "qwen2.5:7b"))

SYSTEM_PROMPT = """You are the final-answer writer for a college information assistant. You are given a user's question plus data gathered by two upstream systems:

- SQL data: exact rows pulled from the college database. Treat this as ground truth — never contradict it, never round or alter its numbers, never omit a fact it contains that the question asked for.
- RAG passages: descriptive text retrieved by semantic search over course/department/faculty/program descriptions. Use this for context, explanation, and descriptive content.

Rules:
- If SQL data is present, it is the source of truth for any specific fact, count, date, or number. If a RAG passage disagrees with SQL data on a fact, go with the SQL data.
- If SQL data is present but empty (no rows), say plainly that no matching records were found — do not invent an answer.
- If RAG passages are present, weave them in naturally for description/context. If none are relevant to the question, ignore them rather than forcing them in.
- If both SQL data and RAG passages are present, merge them into one coherent answer — don't just concatenate two separate answers.
- Write in plain, natural language for the end user. Never mention "SQL agent", "RAG agent", "the router", table/column names, or that this involved multiple systems.
- Be concise. No preamble like "Based on the data provided" — just answer.
"""


def _build_user_prompt(question, route, sql_section, rag_section):
    return f"""User question: {question}

Route: {route}

{sql_section}

{rag_section}

Write the final answer."""


def _messages(question, route, sql_section, rag_section):
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _build_user_prompt(question, route, sql_section, rag_section)},
    ]


def synthesize(question, route, sql_section, rag_section):
    # Raises common.exceptions.LLMUnavailable if Ollama is down/slow.
    content = ollama.chat(
        SYNTHESIS_MODEL,
        messages=_messages(question, route, sql_section, rag_section),
        options={"temperature": 0.2},
    )
    return content.strip()


def synthesize_stream(question, route, sql_section, rag_section):
    """Yields answer text token-by-token as Ollama generates it, so the API
    can stream to the client instead of waiting for the full answer. Raises
    LLMUnavailable if Ollama is down/slow or the stream drops mid-answer."""
    yield from ollama.chat_stream(
        SYNTHESIS_MODEL,
        messages=_messages(question, route, sql_section, rag_section),
        options={"temperature": 0.2},
    )
```

## 96. `backend/synthesis_agent/management/__init__.py`

*1 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.
```

## 97. `backend/synthesis_agent/management/commands/__init__.py`

*1 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.
```

## 98. `backend/synthesis_agent/management/commands/demo_synthesis_agent.py`

*60 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

from django.core.management.base import BaseCommand

from rag_agent.service import retrieve
from sql_agent.service import ask as sql_ask
from synthesis_agent.service import synthesize_answer

# Routes are pre-assigned here (already validated by the router agent in an
# earlier step) so this command can focus on synthesis. Each case actually
# calls the live sql_agent/rag_agent — these are real outputs, not
# copy-pasted text from earlier runs. Includes one deliberately-empty SQL
# case (faculty/programs/etc. are unpopulated) to check the agent reports
# "no data" honestly instead of inventing an answer.
TEST_CASES = [
    {"question": "What courses does the Computer Science department offer?", "route": "SQL"},
    {"question": "Which faculty members work in the Mathematics department?", "route": "SQL"},
    {"question": "Tell me about the Computer Science department.", "route": "RAG"},
    {"question": "What does the Organic Chemistry course cover?", "route": "RAG"},
    {
        "question": "What is the Machine Learning Fundamentals course about, and how many credits is it worth?",
        "route": "BOTH",
    },
]


class Command(BaseCommand):
    help = (
        "Runs 5 test cases through the real SQL and/or RAG agents (per each "
        "case's route) and feeds their actual outputs into the synthesis "
        "agent, printing the upstream data and the final human-readable "
        "answer for review."
    )

    def handle(self, *args, **options):
        for i, case in enumerate(TEST_CASES, 1):
            question = case["question"]
            route = case["route"]
            self.stdout.write(self.style.MIGRATE_HEADING(f"\n[{i}] Q: {question}  (route={route})"))

            sql_result = None
            rag_chunks = None

            if route in ("SQL", "BOTH"):
                sql_result = sql_ask(question, execute=True)
                self.stdout.write(f"    [sql_agent] SQL: {sql_result.generated_sql}")
                if sql_result.error:
                    self.stdout.write(self.style.WARNING(f"    [sql_agent] error: {sql_result.error}"))
                else:
                    self.stdout.write(f"    [sql_agent] rows ({len(sql_result.rows)}): {sql_result.rows}")

            if route in ("RAG", "BOTH"):
                rag_chunks = retrieve(question, top_k=3)
                for c in rag_chunks:
                    self.stdout.write(
                        f"    [rag_agent] [{c.table}#{c.row_id}] score={c.score:.3f} {c.text[:90]}"
                    )

            answer = synthesize_answer(question, route, sql_result=sql_result, rag_chunks=rag_chunks)
            self.stdout.write(self.style.SUCCESS(f"\n    FINAL ANSWER:\n    {answer}"))
```

## 99. `backend/synthesis_agent/service.py`

*65 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

import logging

from . import llm_client

logger = logging.getLogger("synthesis_agent")


def _format_sql_section(sql_result):
    """sql_result is duck-typed to match sql_agent.service.SqlAgentResult:
    .error, .generated_sql, .columns, .rows."""
    if sql_result is None:
        return "SQL data: none."
    if sql_result.error:
        return f"SQL data: query failed ({sql_result.error}) — treat as no data available."
    if not sql_result.rows:
        return f"SQL data: query ran successfully but returned no rows.\nQuery: {sql_result.generated_sql}"

    lines = [f"SQL data (from query: {sql_result.generated_sql}):", f"columns: {sql_result.columns}"]
    for row in sql_result.rows:
        lines.append(f"  {row}")
    return "\n".join(lines)


def _format_rag_section(rag_chunks):
    """rag_chunks is duck-typed to match a list of rag_agent.service.RetrievedChunk:
    .table, .row_id, .score, .text."""
    if not rag_chunks:
        return "RAG passages: none."

    lines = ["RAG passages:"]
    for chunk in rag_chunks:
        lines.append(f"  [{chunk.table}#{chunk.row_id}] (relevance {chunk.score:.2f}) {chunk.text}")
    return "\n".join(lines)


def synthesize_answer(question, route, sql_result=None, rag_chunks=None):
    sql_section = _format_sql_section(sql_result)
    rag_section = _format_rag_section(rag_chunks)

    answer = llm_client.synthesize(question, route, sql_section, rag_section)

    logger.info(
        "question=%r route=%s sql_rows=%d rag_chunks=%d",
        question, route,
        len(sql_result.rows) if sql_result and sql_result.rows else 0,
        len(rag_chunks) if rag_chunks else 0,
    )
    return answer


def synthesize_answer_stream(question, route, sql_result=None, rag_chunks=None):
    """Streaming variant of synthesize_answer: yields the answer in pieces as
    the model generates them."""
    sql_section = _format_sql_section(sql_result)
    rag_section = _format_rag_section(rag_chunks)

    logger.info(
        "streaming question=%r route=%s sql_rows=%d rag_chunks=%d",
        question, route,
        len(sql_result.rows) if sql_result and sql_result.rows else 0,
        len(rag_chunks) if rag_chunks else 0,
    )
    yield from llm_client.synthesize_stream(question, route, sql_section, rag_section)
```

## 100. `backend/verification_agent/__init__.py`

*1 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.
```

## 101. `backend/verification_agent/apps.py`

*8 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

from django.apps import AppConfig


class VerificationAgentConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "verification_agent"
```

## 102. `backend/verification_agent/llm_client.py`

*99 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

import os

import requests

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
# LLM_MODEL is the single knob for the model all agents use; VERIFICATION_MODEL
# is an optional per-agent override that defaults to it.
VERIFICATION_MODEL = os.getenv("VERIFICATION_MODEL", os.getenv("LLM_MODEL", "qwen2.5:7b"))

VERIFY_SYSTEM_PROMPT = """You are a fact-checking verifier for a college information assistant. You are given a final answer that was generated for a user's question, plus the raw source data (SQL query results and/or RAG passages) that answer was supposed to be based on.

Your job: break the answer down into its individual factual claims — specific facts, numbers, names, dates. Skip filler phrases and general statements that don't assert a checkable fact. For EACH claim, check whether it is directly supported by the raw source data provided.

For each claim, output:
- "text": the claim, quoted or closely paraphrased from the answer
- "supported": true if the raw source data directly confirms this claim, false if the source data contradicts it or contains no information about it at all
- "confidence": a number from 0.0 to 1.0 — how confident you are in this supported/not-supported judgment
- "evidence": a short quote or reference to the specific source data that supports or contradicts the claim, or the literal string "no relevant source data found" if there is nothing relevant
- "correct_value": ONLY set this if supported is false AND the source data actually contains the correct fact (i.e. the answer got a real, checkable fact wrong). If supported is false because the claim was invented from nothing the source data ever mentioned, set this to null.

Be strict. The source data is the only ground truth — if a claim isn't in it, it isn't supported, no matter how plausible the claim sounds.

Respond with ONLY a JSON object of the form: {"claims": [...]}
"""

CORRECT_SYSTEM_PROMPT = """You are correcting a previously generated answer for a college information assistant, based on a fact-check that just ran against it.

You will be given the original answer and a list of flagged claims. For each flagged claim:
- If a "correct_value" is given, replace that specific incorrect claim with the correct information, keeping the rest of the answer's wording and flow intact.
- If no correct_value is given (the claim could not be verified against the database at all — it was invented), rewrite that specific part to clearly state it could not be verified against the database. Do not silently delete it without any indication, and do not leave the unverified claim stated as if it were fact.

Leave every part of the answer that was NOT flagged exactly as it was — only touch the flagged parts. Return ONLY the corrected answer text. No explanation, no meta-commentary about the correction process, no mention of "flagged claims" or "verification".
"""


def verify_claims(question, answer, sql_section, rag_section):
    user_prompt = f"""Question: {question}

Raw SQL data:
{sql_section}

Raw RAG passages:
{rag_section}

Answer to verify:
{answer}"""

    resp = requests.post(
        f"{OLLAMA_BASE_URL}/api/chat",
        json={
            "model": VERIFICATION_MODEL,
            "messages": [
                {"role": "system", "content": VERIFY_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "format": "json",
            "stream": False,
            "options": {"temperature": 0},
        },
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["message"]["content"]


def correct_answer(question, original_answer, flagged_claims):
    claims_block = "\n".join(
        f"- claim: {c['text']}\n"
        f"  correct_value: {c['correct_value'] if c.get('correct_value') else 'null (unverifiable — not in source data)'}"
        for c in flagged_claims
    )

    user_prompt = f"""Question: {question}

Original answer:
{original_answer}

Flagged claims:
{claims_block}

Write the corrected answer."""

    resp = requests.post(
        f"{OLLAMA_BASE_URL}/api/chat",
        json={
            "model": VERIFICATION_MODEL,
            "messages": [
                {"role": "system", "content": CORRECT_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "options": {"temperature": 0},
        },
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["message"]["content"].strip()
```

## 103. `backend/verification_agent/management/__init__.py`

*1 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.
```

## 104. `backend/verification_agent/management/commands/__init__.py`

*1 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.
```

## 105. `backend/verification_agent/management/commands/demo_verification_agent.py`

*98 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

from django.core.management.base import BaseCommand
from django.db.models import Count

from rag_agent.service import retrieve
from sql_agent.service import ask as sql_ask
from synthesis_agent.service import synthesize_answer
from verification_agent.models import VerificationLog
from verification_agent.service import verify_and_correct

BASE_CASES = [
    {"question": "What courses does the Computer Science department offer?", "route": "SQL"},
    {"question": "Which faculty members work in the Mathematics department?", "route": "SQL"},
    {"question": "Tell me about the Computer Science department.", "route": "RAG"},
    {"question": "What does the Organic Chemistry course cover?", "route": "RAG"},
    {
        "question": "What is the Machine Learning Fundamentals course about, and how many credits is it worth?",
        "route": "BOTH",
    },
]

# Deliberately fabricated sentences spliced onto a genuine synthesis answer —
# none of this is anywhere in the SQL rows or RAG passages backing each
# case. This is the actual test of whether the verifier catches information
# the synthesis agent (or here, a stand-in for it) added out of nowhere,
# rather than just checking it agrees with itself.
INJECTED_HALLUCINATIONS = [
    " The department also has 12 full-time faculty members specializing in AI research.",
    " The department head is Dr. Jane Smith, who has led the department since 2015.",
    " The department was ranked #1 nationally for computer science education in 2020.",
    " Enrollment is capped at 30 students per semester, with a waiting list typically forming by the second week.",
    " The course is taught by Professor John Doe and maintains an average student rating of 4.8 out of 5.",
]


class Command(BaseCommand):
    help = (
        "Runs 10 test cases through the verification agent: 5 genuine "
        "synthesis answers (checking for false positives) and the same 5 "
        "with a fabricated sentence spliced in (checking the hallucination "
        "catch rate). Every claim check is logged to verification_logs."
    )

    def handle(self, *args, **options):
        run_ids = []
        injected_caught = 0
        genuine_false_positives = 0

        for i, case in enumerate(BASE_CASES, 1):
            question = case["question"]
            route = case["route"]

            sql_result = sql_ask(question, execute=True) if route in ("SQL", "BOTH") else None
            rag_chunks = retrieve(question, top_k=3) if route in ("RAG", "BOTH") else None
            genuine_answer = synthesize_answer(question, route, sql_result=sql_result, rag_chunks=rag_chunks)

            r1 = self._run_case(i, question, route, genuine_answer, sql_result, rag_chunks, injected=False)
            run_ids.append(r1.run_id)
            if any(not c["supported"] for c in r1.claims):
                genuine_false_positives += 1

            hallucinated_answer = genuine_answer + INJECTED_HALLUCINATIONS[i - 1]
            r2 = self._run_case(i + 5, question, route, hallucinated_answer, sql_result, rag_chunks, injected=True)
            run_ids.append(r2.run_id)
            if any(not c["supported"] for c in r2.claims):
                injected_caught += 1

        self.stdout.write(self.style.MIGRATE_HEADING("\n=== Summary ==="))
        self.stdout.write(f"  Injected hallucinations caught: {injected_caught}/5")
        self.stdout.write(f"  Genuine answers with a false-positive flag: {genuine_false_positives}/5")

        self.stdout.write(self.style.MIGRATE_HEADING("\n=== verification_logs tally for this run (real DB query) ==="))
        tally = VerificationLog.objects.filter(run_id__in=run_ids).values("action_taken").annotate(count=Count("id"))
        for row in tally:
            self.stdout.write(f"  {row['action_taken']}: {row['count']}")
        total_claims = VerificationLog.objects.filter(run_id__in=run_ids).count()
        self.stdout.write(f"  total claims logged: {total_claims}")

    def _run_case(self, idx, question, route, answer, sql_result, rag_chunks, injected):
        label = "INJECTED HALLUCINATION" if injected else "genuine"
        self.stdout.write(self.style.MIGRATE_HEADING(f"\n[{idx}] ({label}) Q: {question}"))
        self.stdout.write(f"    answer under test: {answer}")

        result = verify_and_correct(question, route, answer, sql_result=sql_result, rag_chunks=rag_chunks)

        for claim in result.claims:
            verdict = "PASS" if claim["supported"] else "FLAGGED"
            style = self.style.SUCCESS if claim["supported"] else self.style.ERROR
            self.stdout.write(style(f"    [{verdict}] conf={claim['confidence']:.2f}  \"{claim['text']}\""))
            self.stdout.write(f"        evidence: {claim['evidence']}")

        if result.was_corrected:
            self.stdout.write(self.style.WARNING(f"    CORRECTED FINAL ANSWER: {result.final_answer}"))
        else:
            self.stdout.write("    (no correction needed)")

        return result
```

## 106. `backend/verification_agent/migrations/0001_initial.py`

*37 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

# Generated by Django 5.2.16 on 2026-07-24 03:51

import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='VerificationLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('run_id', models.UUIDField(db_index=True, default=uuid.uuid4, editable=False)),
                ('question', models.TextField()),
                ('route', models.CharField(max_length=10)),
                ('original_answer', models.TextField()),
                ('final_answer', models.TextField()),
                ('claim_text', models.TextField()),
                ('supported', models.BooleanField()),
                ('confidence', models.FloatField()),
                ('evidence', models.TextField(blank=True)),
                ('action_taken', models.CharField(choices=[('passed', 'Passed'), ('corrected', 'Corrected using source data'), ('flagged_unverifiable', 'Flagged as unverifiable')], max_length=25)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'db_table': 'verification_logs',
            },
        ),
    ]
```

## 107. `backend/verification_agent/migrations/__init__.py`

*1 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.
```

## 108. `backend/verification_agent/models.py`

*43 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

import uuid

from django.db import models


class VerificationLog(models.Model):
    """One row per factual claim checked, not per question — this is what
    makes a claim-level hallucination catch-rate computable later, e.g.:

        SELECT action_taken, count(*) FROM verification_logs GROUP BY action_taken;

    Lives in the app-owner's database (not rag_agent_ro's schema) since this
    is internal audit data about the agents, not college data the RAG agent
    should ever read.
    """

    ACTION_CHOICES = [
        ("passed", "Passed"),
        ("corrected", "Corrected using source data"),
        ("flagged_unverifiable", "Flagged as unverifiable"),
    ]

    run_id = models.UUIDField(default=uuid.uuid4, editable=False, db_index=True)
    question = models.TextField()
    route = models.CharField(max_length=10)
    original_answer = models.TextField()
    final_answer = models.TextField()

    claim_text = models.TextField()
    supported = models.BooleanField()
    confidence = models.FloatField()
    evidence = models.TextField(blank=True)
    action_taken = models.CharField(max_length=25, choices=ACTION_CHOICES)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "verification_logs"

    def __str__(self):
        return f"[{self.action_taken}] {self.claim_text[:50]}"
```

## 109. `backend/verification_agent/service.py`

*133 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

import json
import logging
import re
import uuid

from . import llm_client
from .models import VerificationLog

logger = logging.getLogger("verification_agent")

_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


class VerificationResult:
    def __init__(self, question, original_answer, final_answer, claims, was_corrected):
        self.question = question
        self.original_answer = original_answer
        self.final_answer = final_answer
        self.claims = claims
        self.was_corrected = was_corrected
        self.run_id = None  # set by verify_and_correct after logging


def _format_sql_section(sql_result):
    if sql_result is None:
        return "SQL data: none."
    if sql_result.error:
        return f"SQL data: query failed ({sql_result.error}) — treat as no data available."
    if not sql_result.rows:
        return f"SQL data: query ran successfully but returned no rows.\nQuery: {sql_result.generated_sql}"
    lines = [f"SQL data (from query: {sql_result.generated_sql}):", f"columns: {sql_result.columns}"]
    for row in sql_result.rows:
        lines.append(f"  {row}")
    return "\n".join(lines)


def _format_rag_section(rag_chunks):
    if not rag_chunks:
        return "RAG passages: none."
    lines = ["RAG passages:"]
    for chunk in rag_chunks:
        lines.append(f"  [{chunk.table}#{chunk.row_id}] (relevance {chunk.score:.2f}) {chunk.text}")
    return "\n".join(lines)


def _parse_claims(raw_output):
    text = _CODE_FENCE_RE.sub("", raw_output).strip()
    try:
        parsed = json.loads(text)
        raw_claims = parsed.get("claims", [])
    except (json.JSONDecodeError, AttributeError) as exc:
        logger.warning("failed to parse verification output raw=%r error=%s", raw_output, exc)
        return []

    claims = []
    for c in raw_claims:
        try:
            claims.append(
                {
                    "text": str(c["text"]),
                    "supported": bool(c["supported"]),
                    "confidence": float(c.get("confidence", 0.5)),
                    "evidence": str(c.get("evidence", "")),
                    "correct_value": c.get("correct_value") or None,
                }
            )
        except (KeyError, TypeError, ValueError):
            logger.warning("skipping malformed claim entry: %r", c)
    return claims


def verify_and_correct(question, route, answer, sql_result=None, rag_chunks=None):
    """Checks every factual claim in `answer` against the raw SQL/RAG data
    it was supposedly built from. Logs one VerificationLog row per claim
    (this is what makes a hallucination catch-rate computable later), and
    if any claim was flagged, produces a corrected final answer — either
    fixed from source data, or annotated as unverifiable.
    """
    sql_section = _format_sql_section(sql_result)
    rag_section = _format_rag_section(rag_chunks)

    raw_output = llm_client.verify_claims(question, answer, sql_section, rag_section)
    claims = _parse_claims(raw_output)

    flagged_claims = [c for c in claims if not c["supported"]]

    if flagged_claims:
        final_answer = llm_client.correct_answer(question, answer, flagged_claims)
    else:
        final_answer = answer

    run_id = uuid.uuid4()
    log_rows = []
    for claim in claims:
        if claim["supported"]:
            action = "passed"
        elif claim["correct_value"]:
            action = "corrected"
        else:
            action = "flagged_unverifiable"

        log_rows.append(
            VerificationLog(
                run_id=run_id,
                question=question,
                route=route,
                original_answer=answer,
                final_answer=final_answer,
                claim_text=claim["text"],
                supported=claim["supported"],
                confidence=claim["confidence"],
                evidence=claim["evidence"],
                action_taken=action,
            )
        )
    VerificationLog.objects.bulk_create(log_rows)

    logger.info(
        "question=%r claims=%d flagged=%d corrected=%s run_id=%s",
        question, len(claims), len(flagged_claims), final_answer != answer, run_id,
    )

    result = VerificationResult(
        question=question,
        original_answer=answer,
        final_answer=final_answer,
        claims=claims,
        was_corrected=(final_answer != answer),
    )
    result.run_id = run_id
    return result
```

# Sync Worker - Incremental Embedding Pipeline

## 110. `sync_worker/Dockerfile`

*19 lines*

```text
# Copyright (c) 2026 Yash Garad. All rights reserved.

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]
```

## 111. `sync_worker/chunker.py`

*52 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

DEGREE_LABELS = {
    "bachelor": "Bachelor's",
    "master": "Master's",
    "diploma": "Diploma",
    "phd": "PhD",
}


def _department_to_text(row, dept_lookup):
    parts = [f"Department: {row['name']} (code: {row['code']})."]
    if row.get("established_year"):
        parts.append(f"Established in {row['established_year']}.")
    return " ".join(parts)


def _faculty_to_text(row, dept_lookup):
    dept_name = dept_lookup.get(row.get("department_id"), "an unspecified department")
    parts = [f"{row['first_name']} {row['last_name']} is a faculty member in the {dept_name} department."]
    if row.get("designation"):
        parts.append(f"Designation: {row['designation']}.")
    return " ".join(parts)


def _program_to_text(row, dept_lookup):
    dept_name = dept_lookup.get(row.get("department_id"), "an unspecified department")
    degree = DEGREE_LABELS.get(row.get("degree_level"), row.get("degree_level"))
    return (
        f"{row['name']} is a {degree} program offered by the {dept_name} department, "
        f"with a duration of {row['duration_years']} years."
    )


def _course_to_text(row, dept_lookup):
    dept_name = dept_lookup.get(row.get("department_id"), "an unspecified department")
    text = f"{row['code']}: {row['title']}. Offered by the {dept_name} department, worth {row['credits']} credits."
    if row.get("description"):
        text += f" {row['description']}"
    return text


_TEMPLATES = {
    "departments": _department_to_text,
    "faculty": _faculty_to_text,
    "programs": _program_to_text,
    "courses": _course_to_text,
}


def row_to_text(table, row, dept_lookup):
    return _TEMPLATES[table](row, dept_lookup)
```

## 112. `sync_worker/config.py`

*51 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

import os

from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("RAG_AGENT_RO_HOST", os.getenv("POSTGRES_HOST", "postgres")),
    "port": os.getenv("RAG_AGENT_RO_PORT", os.getenv("POSTGRES_PORT", "5432")),
    "dbname": os.getenv("RAG_AGENT_RO_DB", os.getenv("POSTGRES_DB", "college_rag")),
    "user": os.getenv("RAG_AGENT_RO_USER", "rag_agent_ro"),
    "password": os.getenv("RAG_AGENT_RO_PASSWORD"),
}

POLL_INTERVAL_SECONDS = int(os.getenv("SYNC_WORKER_POLL_INTERVAL_SECONDS", "30"))

DATA_DIR = os.getenv("SYNC_WORKER_DATA_DIR", "data")
STATE_FILE = os.path.join(DATA_DIR, "state.json")
QUEUE_FILE = os.path.join(DATA_DIR, "change_queue.jsonl")

# Same set of tables rag_agent_ro is granted SELECT on (see
# db/sql/create_rag_agent_ro.sql) — general institutional data only, never
# the per-student tables (students, enrollments, attendance, exam_results,
# fee_payments). `courses_prerequisites` is also skipped: it's a bare M2M
# join table with no updated_at column of its own to poll against.
TABLES = [
    "departments",
    "faculty",
    "programs",
    "courses",
    "rooms",
    "course_offerings",
    "class_schedule",
    "exam_timetable",
    "fee_structure",
]

# Of the tables above, only these have free-text content worth semantic
# search (names, descriptions, designations). The rest — rooms, schedules,
# timetables, fee amounts — are structured/numeric and better served by
# direct SQL lookups than a vector store, so they're never embedded.
DESCRIPTIVE_TABLES = ["departments", "faculty", "programs", "courses"]

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "768"))

QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "college_docs")
```

## 113. `sync_worker/embedder.py`

*21 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

import requests

import config


def embed_text(text):
    resp = requests.post(
        f"{config.OLLAMA_BASE_URL}/api/embeddings",
        json={"model": config.EMBEDDING_MODEL, "prompt": text},
        timeout=60,
    )
    resp.raise_for_status()
    embedding = resp.json()["embedding"]
    if len(embedding) != config.EMBEDDING_DIM:
        raise ValueError(
            f"expected a {config.EMBEDDING_DIM}-dim embedding from {config.EMBEDDING_MODEL}, "
            f"got {len(embedding)} — did the model change?"
        )
    return embedding
```

## 114. `sync_worker/lookups.py`

*8 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

def fetch_department_lookup(conn):
    """id -> name for every department, used to resolve FKs when chunking
    faculty/program/course rows into readable text (see chunker.py)."""
    with conn.cursor() as cur:
        cur.execute("SELECT id, name FROM departments;")
        return {row[0]: row[1] for row in cur.fetchall()}
```

## 115. `sync_worker/main.py`

*105 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

import logging
import time
from datetime import datetime

import psycopg2

import config
import state as state_module
from chunker import row_to_text
from embedder import embed_text
from lookups import fetch_department_lookup
from poller import poll_table
from queue_writer import append_changes
from vector_store import upsert_point

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [sync_worker] %(levelname)s: %(message)s",
)
logger = logging.getLogger("sync_worker")


def connect():
    return psycopg2.connect(**config.DB_CONFIG)


def embed_and_upsert_changes(table, changes, dept_lookup):
    for change in changes:
        try:
            text = row_to_text(table, change["row"], dept_lookup)
            vector = embed_text(text)
            upsert_point(table, change["pk"], vector, text, change["updated_at"])
            logger.info("embedded %s id=%s -> %s", table, change["pk"], text[:80])
        except Exception:
            # One bad row/embedding call shouldn't take down the whole cycle —
            # it'll simply be retried next cycle since the watermark for this
            # table only advances after this loop finishes successfully.
            logger.exception("failed to embed/upsert %s id=%s", table, change["pk"])
            raise


def run_cycle(conn, app_state):
    total_changes = 0
    dept_lookup = fetch_department_lookup(conn)

    for table in config.TABLES:
        entry = app_state.get(table, {})
        last_updated_at = datetime.fromisoformat(entry.get("last_updated_at", state_module.EPOCH))
        seen_ids = set(entry.get("seen_ids_at_last_ts", []))

        changes, new_last_updated_at, new_seen_ids = poll_table(conn, table, last_updated_at, seen_ids)

        if changes:
            for change in changes:
                logger.info(
                    "%-18s %-8s id=%-5s updated_at=%s",
                    table, change["op"], change["pk"], change["updated_at"],
                )
            append_changes(changes)
            total_changes += len(changes)

            if table in config.DESCRIPTIVE_TABLES:
                embed_and_upsert_changes(table, changes, dept_lookup)

        app_state[table] = {
            "last_updated_at": new_last_updated_at.isoformat(),
            "seen_ids_at_last_ts": sorted(new_seen_ids),
        }
        # Persist after every table, not just at the end of the cycle, so a
        # crash mid-cycle doesn't re-process tables already handled this run.
        state_module.save_state(app_state)

    if total_changes:
        logger.info("poll cycle complete: %d change(s) detected", total_changes)
    else:
        logger.info("poll cycle complete: no changes detected")


def main():
    logger.info("sync_worker starting")
    logger.info("polling tables: %s", ", ".join(config.TABLES))
    logger.info("embedding + upserting to Qdrant for: %s", ", ".join(config.DESCRIPTIVE_TABLES))
    logger.info("poll interval: %ds", config.POLL_INTERVAL_SECONDS)

    app_state = state_module.load_state()

    while True:
        try:
            conn = connect()
            try:
                run_cycle(conn, app_state)
            finally:
                conn.close()
        except psycopg2.Error as exc:
            logger.error("database error during poll cycle: %s", exc)
        except Exception:
            logger.exception("unexpected error during poll cycle")

        time.sleep(config.POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
```

## 116. `sync_worker/poller.py`

*63 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

import decimal

import psycopg2.extras
from psycopg2 import sql


def _json_safe(value):
    if isinstance(value, decimal.Decimal):
        return float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def poll_table(conn, table, last_updated_at, seen_ids_at_last_ts):
    """Fetch rows changed since the watermark, classify each as new/updated.

    Watermark is a (last_updated_at, seen_ids_at_last_ts) pair rather than a
    bare timestamp: polling with `updated_at >= watermark` can re-fetch rows
    already processed in a prior cycle if several rows share the exact same
    updated_at as the watermark, so seen_ids_at_last_ts lets us skip those
    without risking `>` silently dropping same-timestamp rows we haven't
    seen yet.
    """
    query = sql.SQL(
        "SELECT * FROM {table} WHERE updated_at >= %s ORDER BY updated_at ASC, id ASC;"
    ).format(table=sql.Identifier(table))

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(query, (last_updated_at,))
        rows = cur.fetchall()

    changes = []
    new_last_updated_at = last_updated_at
    new_seen_ids = set(seen_ids_at_last_ts)

    for row in rows:
        row_id = row["id"]
        row_updated_at = row["updated_at"]

        if row_updated_at == last_updated_at and row_id in seen_ids_at_last_ts:
            continue

        op = "new" if row["created_at"] == row["updated_at"] else "updated"
        changes.append(
            {
                "table": table,
                "op": op,
                "pk": row_id,
                "updated_at": row_updated_at.isoformat(),
                "row": {k: _json_safe(v) for k, v in row.items()},
            }
        )

        if row_updated_at > new_last_updated_at:
            new_last_updated_at = row_updated_at
            new_seen_ids = {row_id}
        elif row_updated_at == new_last_updated_at:
            new_seen_ids.add(row_id)

    return changes, new_last_updated_at, new_seen_ids
```

## 117. `sync_worker/queue_writer.py`

*13 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

import json
import os

import config


def append_changes(changes):
    os.makedirs(config.DATA_DIR, exist_ok=True)
    with open(config.QUEUE_FILE, "a", encoding="utf-8") as f:
        for change in changes:
            f.write(json.dumps(change) + "\n")
```

## 118. `sync_worker/requirements.txt`

*6 lines*

```text
# Copyright (c) 2026 Yash Garad. All rights reserved.

python-dotenv>=1.0
psycopg2-binary>=2.9
qdrant-client>=1.9
requests>=2.32
```

## 119. `sync_worker/state.py`

*26 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

import json
import os

import config

# Sentinel watermark used the first time a table is ever polled — everything
# currently in the table is >= this, so the first cycle reports a full
# initial sync rather than silently skipping pre-existing rows.
EPOCH = "1970-01-01T00:00:00+00:00"


def load_state():
    if not os.path.exists(config.STATE_FILE):
        return {}
    with open(config.STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(state):
    os.makedirs(config.DATA_DIR, exist_ok=True)
    tmp_path = config.STATE_FILE + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp_path, config.STATE_FILE)
```

## 120. `sync_worker/test_embedding_pipeline.py`

*161 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

"""
Seeds 5 sample courses covering distinct topics, runs them through the same
chunk -> embed -> upsert pipeline main.py uses, then fires 5 natural-language
queries at Qdrant and checks the expected course comes back in the top 3
results for each. Exercises the real chunker/embedder/vector_store code —
nothing here is mocked.

Requires the Postgres owner credentials (POSTGRES_*), not rag_agent_ro,
because it needs to INSERT — sync_worker itself only ever reads.

Usage: docker compose exec backend ... no — run inside the sync_worker
container: docker compose exec sync_worker python test_embedding_pipeline.py
"""

import logging
import os
import sys

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

from chunker import row_to_text
from embedder import embed_text
from lookups import fetch_department_lookup
from vector_store import search, upsert_point

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [test] %(levelname)s: %(message)s")
logger = logging.getLogger("test_embedding_pipeline")

SUPERUSER_DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "postgres"),
    "port": os.getenv("POSTGRES_PORT", "5432"),
    "dbname": os.getenv("POSTGRES_DB", "college_rag"),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD"),
}

SAMPLE_COURSES = [
    dict(
        code="TEST-CS501",
        title="Machine Learning Fundamentals",
        credits=4,
        description="Covers supervised and unsupervised learning, neural networks, and model evaluation.",
    ),
    dict(
        code="TEST-CS310",
        title="Database Systems",
        credits=3,
        description="Relational algebra, SQL, normalization, transactions, and indexing.",
    ),
    dict(
        code="TEST-CHEM210",
        title="Organic Chemistry I",
        credits=4,
        description="Structure, nomenclature, and reactions of organic compounds.",
    ),
    dict(
        code="TEST-ENG150",
        title="Shakespearean Literature",
        credits=3,
        description="Close reading of major tragedies and comedies by William Shakespeare.",
    ),
    dict(
        code="TEST-FIN220",
        title="Financial Accounting",
        credits=3,
        description="Principles of recording, summarizing, and reporting financial transactions.",
    ),
]

TEST_QUERIES = [
    ("Which course teaches neural networks and AI models?", "TEST-CS501"),
    ("I want to learn SQL and how databases work.", "TEST-CS310"),
    ("A course about chemical reactions and molecules.", "TEST-CHEM210"),
    ("Looking for a class on Shakespeare's plays.", "TEST-ENG150"),
    ("How do I learn about company financial statements?", "TEST-FIN220"),
]


def seed_sample_courses(conn, department_id):
    rows = []
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        for course in SAMPLE_COURSES:
            cur.execute(
                """
                INSERT INTO courses (code, title, credits, department_id, description, created_at, updated_at)
                VALUES (%(code)s, %(title)s, %(credits)s, %(department_id)s, %(description)s, now(), now())
                ON CONFLICT (code) DO UPDATE SET
                    title = EXCLUDED.title,
                    credits = EXCLUDED.credits,
                    description = EXCLUDED.description,
                    updated_at = now()
                RETURNING *;
                """,
                {**course, "department_id": department_id},
            )
            rows.append(dict(cur.fetchone()))
    conn.commit()
    return rows


def embed_and_upsert(rows, dept_lookup):
    code_to_id = {}
    for row in rows:
        for key in ("created_at", "updated_at"):
            if row.get(key) is not None:
                row[key] = row[key].isoformat()
        text = row_to_text("courses", row, dept_lookup)
        vector = embed_text(text)
        upsert_point("courses", row["id"], vector, text, row["updated_at"])
        code_to_id[row["code"]] = row["id"]
        logger.info("embedded %s -> %s", row["code"], text[:90])
    return code_to_id


def run_queries(code_to_id):
    id_to_code = {v: k for k, v in code_to_id.items()}
    passed = 0
    for query, expected_code in TEST_QUERIES:
        vector = embed_text(query)
        results = search(vector, limit=3, table_filter="courses")
        found_codes = [id_to_code.get(r.payload.get("row_id"), f"other:{r.payload.get('row_id')}") for r in results]
        ok = expected_code in found_codes
        passed += int(ok)
        logger.info(
            "query=%r top_matches=%s expected=%s -> %s",
            query, found_codes, expected_code, "PASS" if ok else "FAIL",
        )
    logger.info("%d/%d queries returned the expected course in the top 3 results", passed, len(TEST_QUERIES))
    return passed == len(TEST_QUERIES)


def main():
    conn = psycopg2.connect(**SUPERUSER_DB_CONFIG)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM departments ORDER BY id LIMIT 1;")
            row = cur.fetchone()
            if row is None:
                raise RuntimeError("No department found in the database — seed at least one department first.")
            department_id = row[0]

        dept_lookup = fetch_department_lookup(conn)
        rows = seed_sample_courses(conn, department_id)
        logger.info("inserted/updated %d sample course rows", len(rows))
    finally:
        conn.close()

    code_to_id = embed_and_upsert(rows, dept_lookup)
    all_passed = run_queries(code_to_id)

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
```

## 121. `sync_worker/vector_store.py`

*67 lines*

```python
# Copyright (c) 2026 Yash Garad. All rights reserved.

import uuid

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, FieldCondition, Filter, MatchValue, PointStruct, VectorParams

import config

_client = None


def get_client():
    global _client
    if _client is None:
        _client = QdrantClient(url=config.QDRANT_URL)
        _ensure_collection(_client)
    return _client


def _ensure_collection(client):
    existing = {c.name for c in client.get_collections().collections}
    if config.QDRANT_COLLECTION not in existing:
        client.create_collection(
            collection_name=config.QDRANT_COLLECTION,
            vectors_config=VectorParams(size=config.EMBEDDING_DIM, distance=Distance.COSINE),
        )


def point_id_for(table, pk):
    # Deterministic UUID from (table, pk) so re-embedding the same row on a
    # later sync updates its existing point instead of creating a duplicate.
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{table}:{pk}"))


def upsert_point(table, pk, vector, text, last_updated):
    client = get_client()
    client.upsert(
        collection_name=config.QDRANT_COLLECTION,
        points=[
            PointStruct(
                id=point_id_for(table, pk),
                vector=vector,
                payload={
                    "table": table,
                    "row_id": pk,
                    "last_updated": last_updated,
                    "text": text,
                },
            )
        ],
    )


def search(query_vector, limit=5, table_filter=None):
    client = get_client()
    query_filter = None
    if table_filter:
        query_filter = Filter(must=[FieldCondition(key="table", match=MatchValue(value=table_filter))])

    response = client.query_points(
        collection_name=config.QDRANT_COLLECTION,
        query=query_vector,
        limit=limit,
        query_filter=query_filter,
    )
    return response.points
```

# Frontend - React Client

## 122. `frontend/Dockerfile`

*14 lines*

```text
# Copyright (c) 2026 Yash Garad. All rights reserved.

FROM node:20-alpine

WORKDIR /app

COPY package.json ./
RUN npm install

COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev"]
```

## 123. `frontend/index.html`

*13 lines*

```html
<!doctype html>
<!-- Copyright (c) 2026 Yash Garad. All rights reserved. -->
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>College RAG</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
```

## 124. `frontend/package.json`

*25 lines*

```json
{
  "name": "college-rag-frontend",
  "private": true,
  "version": "0.0.1",
  "type": "module",
  "author": "Yash Garad",
  "license": "SEE LICENSE IN LICENSE",
  "copyright": "Copyright (c) 2026 Yash Garad. All rights reserved.",
  "scripts": {
    "dev": "vite --host 0.0.0.0",
    "build": "vite build",
    "preview": "vite preview --host 0.0.0.0"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1"
  },
  "devDependencies": {
    "@vitejs/plugin-react": "^4.3.1",
    "autoprefixer": "^10.4.19",
    "postcss": "^8.4.38",
    "tailwindcss": "^3.4.4",
    "vite": "^5.3.1"
  }
}
```

## 125. `frontend/postcss.config.js`

*8 lines*

```javascript
// Copyright (c) 2026 Yash Garad. All rights reserved.

export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
};
```

## 126. `frontend/src/App.jsx`

*51 lines*

```jsx
// Copyright (c) 2026 Yash Garad. All rights reserved.

import { useEffect, useState } from "react";

import Chat from "./components/Chat";
import Login from "./components/Login";
import { ensureCsrf, getMe, logout } from "./api";

function App() {
  const [username, setUsername] = useState(null);
  const [loading, setLoading] = useState(true);

  // On load: make sure we have a CSRF cookie, then ask the server whether we
  // already have a valid session (rather than trusting any client-side state).
  useEffect(() => {
    (async () => {
      await ensureCsrf();
      const me = await getMe();
      setUsername(me?.username ?? null);
      setLoading(false);
    })();
  }, []);

  async function handleLogout() {
    await logout();
    setUsername(null);
  }

  function handleSessionExpired() {
    // Session was rejected mid-use — bounce back to login.
    setUsername(null);
  }

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-900 text-slate-400">
        Loading…
      </div>
    );
  }

  if (!username) {
    return <Login onLoggedIn={setUsername} />;
  }

  return (
    <Chat username={username} onLogout={handleLogout} onSessionExpired={handleSessionExpired} />
  );
}

export default App;
```

## 127. `frontend/src/api.js`

*120 lines*

```javascript
// Copyright (c) 2026 Yash Garad. All rights reserved.

// Session-cookie auth: the browser holds an httpOnly session cookie (not
// readable by JS), and we send Django's CSRF token from the csrftoken cookie
// as the X-CSRFToken header on every unsafe (POST) request. Nothing sensitive
// is kept in localStorage.

function getCookie(name) {
  const match = document.cookie.match(new RegExp("(^|;\\s*)" + name + "=([^;]*)"));
  return match ? decodeURIComponent(match[2]) : null;
}

// Ask the server to set the csrftoken cookie. Call once before the first POST.
export async function ensureCsrf() {
  await fetch("/api/auth/csrf/", { credentials: "include" }).catch(() => {});
}

function csrfHeaders() {
  const token = getCookie("csrftoken");
  return token ? { "X-CSRFToken": token } : {};
}

export async function login(username, password) {
  await ensureCsrf();
  const res = await fetch("/api/auth/login/", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json", ...csrfHeaders() },
    body: JSON.stringify({ username, password }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.error || `Login failed (${res.status})`);
  }
  return data; // { username, is_staff }
}

export async function logout() {
  await fetch("/api/auth/logout/", {
    method: "POST",
    credentials: "include",
    headers: { ...csrfHeaders() },
  }).catch(() => {});
}

// Returns { username, is_staff } if a valid session exists, or null otherwise.
export async function getMe() {
  const res = await fetch("/api/auth/me/", { credentials: "include" });
  if (!res.ok) return null;
  return res.json();
}

/**
 * POST a question to /api/ask/ and stream the SSE response. Callbacks:
 *   onMeta(meta), onToken(text), onDone(final), onError(msg).
 * Returns a promise that resolves when the stream ends.
 */
export async function askStream(question, { onMeta, onToken, onDone, onError }) {
  const res = await fetch("/api/ask/", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json", ...csrfHeaders() },
    body: JSON.stringify({ question }),
  });

  if (res.status === 401 || res.status === 403) {
    onError?.("Your session is not authorized. Please log in again.");
    return { unauthorized: true };
  }
  if (res.status === 429) {
    onError?.("You're sending questions too quickly. Please wait a moment and try again.");
    return { throttled: true };
  }
  if (!res.ok || !res.body) {
    const data = await res.json().catch(() => ({}));
    onError?.(data.error || `Request failed (${res.status})`);
    return {};
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  // SSE frames are separated by a blank line; parse them as they complete.
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let sep;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const frame = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      handleFrame(frame, { onMeta, onToken, onDone, onError });
    }
  }
  return {};
}

function handleFrame(frame, { onMeta, onToken, onDone, onError }) {
  let event = "message";
  let dataLine = "";
  for (const line of frame.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLine += line.slice(5).trim();
  }
  if (!dataLine) return;

  let payload;
  try {
    payload = JSON.parse(dataLine);
  } catch {
    return;
  }

  if (event === "meta") onMeta?.(payload);
  else if (event === "token") onToken?.(payload.text || "");
  else if (event === "done") onDone?.(payload.answer || "");
  else if (event === "error") onError?.(payload.error || "Unknown error");
}
```

## 128. `frontend/src/components/Chat.jsx`

*138 lines*

```jsx
// Copyright (c) 2026 Yash Garad. All rights reserved.

import { useEffect, useRef, useState } from "react";

import { askStream } from "../api";

function RouteBadge({ route }) {
  if (!route) return null;
  const colors = {
    SQL: "bg-sky-900 text-sky-300",
    RAG: "bg-violet-900 text-violet-300",
    BOTH: "bg-amber-900 text-amber-300",
  };
  return (
    <span className={`ml-2 rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${colors[route] || "bg-slate-700 text-slate-300"}`}>
      {route}
    </span>
  );
}

function Chat({ username, onLogout, onSessionExpired }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const scrollRef = useRef(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  async function handleSubmit(e) {
    e.preventDefault();
    const question = input.trim();
    if (!question || busy) return;

    setInput("");
    setBusy(true);
    setMessages((prev) => [...prev, { role: "user", text: question }]);
    // Placeholder assistant message we fill in as tokens stream in.
    const assistantIndex = messages.length + 1;
    setMessages((prev) => [...prev, { role: "assistant", text: "", route: null, pending: true }]);

    const update = (patch) =>
      setMessages((prev) => {
        const next = [...prev];
        next[assistantIndex] = { ...next[assistantIndex], ...patch(next[assistantIndex]) };
        return next;
      });

    let expired = false;
    const result = await askStream(question, {
      onMeta: (meta) => update((m) => ({ route: meta.route, pending: true })),
      onToken: (text) => update((m) => ({ text: m.text + text, pending: false })),
      onDone: (final) => update((m) => ({ text: final || m.text, pending: false })),
      onError: (msg) => {
        if (msg.toLowerCase().includes("authorized")) expired = true;
        update((m) => ({ text: m.text || `⚠️ ${msg}`, error: true, pending: false }));
      },
    }).catch((err) => {
      update((m) => ({ text: `⚠️ ${err.message}`, error: true, pending: false }));
      return {};
    });

    setBusy(false);
    if (expired || result?.unauthorized) onSessionExpired();
  }

  return (
    <div className="flex h-screen flex-col bg-slate-900 text-slate-100">
      <header className="flex items-center justify-between border-b border-slate-700 px-6 py-3">
        <h1 className="text-lg font-semibold">College Assistant</h1>
        <div className="flex items-center gap-3 text-sm text-slate-400">
          <span>{username}</span>
          <button
            onClick={onLogout}
            className="rounded border border-slate-600 px-2 py-1 text-slate-300 transition hover:bg-slate-800"
          >
            Sign out
          </button>
        </div>
      </header>

      <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto px-6 py-6">
        {messages.length === 0 && (
          <div className="mx-auto mt-20 max-w-md text-center text-slate-500">
            <p className="text-lg">Ask a question about courses, departments, faculty, fees, or schedules.</p>
          </div>
        )}

        {messages.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
            <div
              className={`max-w-2xl whitespace-pre-wrap rounded-2xl px-4 py-2.5 ${
                msg.role === "user"
                  ? "bg-emerald-600 text-white"
                  : msg.error
                    ? "bg-red-950 text-red-200"
                    : "bg-slate-800 text-slate-100"
              }`}
            >
              {msg.role === "assistant" && msg.route && (
                <div className="mb-1 text-xs text-slate-400">
                  Assistant <RouteBadge route={msg.route} />
                </div>
              )}
              {msg.text}
              {msg.role === "assistant" && msg.pending && (
                <span className="ml-1 inline-block h-4 w-2 animate-pulse bg-slate-400 align-middle" />
              )}
            </div>
          </div>
        ))}
      </div>

      <form onSubmit={handleSubmit} className="border-t border-slate-700 px-6 py-4">
        <div className="flex gap-3">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask a question…"
            disabled={busy}
            className="flex-1 rounded-lg border border-slate-600 bg-slate-800 px-4 py-2.5 text-slate-100 outline-none focus:border-emerald-500 disabled:opacity-60"
          />
          <button
            type="submit"
            disabled={busy || !input.trim()}
            className="rounded-lg bg-emerald-600 px-5 py-2.5 font-medium text-white transition hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {busy ? "…" : "Send"}
          </button>
        </div>
      </form>
    </div>
  );
}

export default Chat;
```

## 129. `frontend/src/components/Login.jsx`

*69 lines*

```jsx
// Copyright (c) 2026 Yash Garad. All rights reserved.

import { useState } from "react";

import { login } from "../api";

function Login({ onLoggedIn }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const { username: name } = await login(username, password);
      onLoggedIn(name);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-900 px-4 text-slate-100">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm rounded-xl border border-slate-700 bg-slate-800 p-8 shadow-lg"
      >
        <h1 className="mb-1 text-2xl font-bold">College Assistant</h1>
        <p className="mb-6 text-sm text-slate-400">Staff sign-in required</p>

        <label className="mb-1 block text-sm font-medium text-slate-300">Username</label>
        <input
          type="text"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          autoFocus
          required
          className="mb-4 w-full rounded-lg border border-slate-600 bg-slate-900 px-3 py-2 text-slate-100 outline-none focus:border-emerald-500"
        />

        <label className="mb-1 block text-sm font-medium text-slate-300">Password</label>
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          className="mb-4 w-full rounded-lg border border-slate-600 bg-slate-900 px-3 py-2 text-slate-100 outline-none focus:border-emerald-500"
        />

        {error && <p className="mb-4 text-sm text-red-400">{error}</p>}

        <button
          type="submit"
          disabled={loading}
          className="w-full rounded-lg bg-emerald-600 py-2 font-medium text-white transition hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {loading ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}

export default Login;
```

## 130. `frontend/src/index.css`

*5 lines*

```css
/* Copyright (c) 2026 Yash Garad. All rights reserved. */

@tailwind base;
@tailwind components;
@tailwind utilities;
```

## 131. `frontend/src/main.jsx`

*13 lines*

```jsx
// Copyright (c) 2026 Yash Garad. All rights reserved.

import React from "react";
import ReactDOM from "react-dom/client";

import App from "./App.jsx";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
```

## 132. `frontend/tailwind.config.js`

*10 lines*

```javascript
// Copyright (c) 2026 Yash Garad. All rights reserved.

/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {},
  },
  plugins: [],
};
```

## 133. `frontend/vite.config.js`

*21 lines*

```javascript
// Copyright (c) 2026 Yash Garad. All rights reserved.

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 5173,
    // The Caddy proxy forwards requests with the server's hostname/IP as the
    // Host header; allow any host so Vite's dev server doesn't reject them.
    allowedHosts: true,
    proxy: {
      "/api": {
        target: process.env.VITE_API_PROXY_TARGET || "http://backend:8000",
        changeOrigin: true,
      },
    },
  },
});
```
