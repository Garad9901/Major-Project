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

## Loading the faculty development dataset

The assistant answers questions about a real imported dataset of **13,000 anonymised
faculty development survey records** (no names, no emails — the key is an opaque code
like `FAC_00001`).

**Where the source file lives**

| | |
| --- | --- |
| Original download | `C:\Users\Yash\Downloads\archive (12)\big_data_faculty_development_dataset.csv` |
| Inside the container | `/tmp/faculty_development.csv` (copied in by the step below) |
| Size / shape | ~3 MB, 13,000 data rows, 34 columns |

Keep the original CSV somewhere durable — `Downloads` is not a safe long-term home. The
loader needs it again only if you rebuild the database from scratch.

### Re-running the load from scratch

**It is safe to run this as many times as you like.** Both writes are *upserts* keyed on
natural keys (`faculty_id` for the records, `scope` + `scope_key` for the summaries), so
re-running updates rows in place and never duplicates them.

```
docker compose cp "C:\Users\Yash\Downloads\archive (12)\big_data_faculty_development_dataset.csv" backend:/tmp/faculty_development.csv
docker compose exec backend python manage.py load_faculty_dataset --csv /tmp/faculty_development.csv
```

Expected output the first time:
```
Parsed 13,000 rows from /tmp/faculty_development.csv
  13,000 new, 0 existing (will be updated in place), 0 in the database but absent from this CSV
faculty_development now holds 13,000 rows.
faculty_development_profiles: 55 created, 0 updated, 0 unchanged (55 total).
```

Expected output on a re-run — note **0 new** and the row count unchanged:
```
  0 new, 13,000 existing (will be updated in place), 0 in the database but absent from this CSV
faculty_development now holds 13,000 rows.
faculty_development_profiles: 0 created, 0 updated, 55 unchanged (55 total).
```

**Useful options**

| Option | What it does |
| --- | --- |
| `--dry-run` | Parse and validate the file, report what *would* change, write nothing. Always worth doing first. |
| `--profiles-only` | Skip the CSV; just rebuild the 55 prose summaries from rows already loaded. |
| `--prune` | Also **delete** records whose ID is missing from the CSV. Off by default so a truncated file can't silently destroy data. |

The loader refuses to run rather than guess if the CSV's columns don't match what it
expects, if a value is empty, or if an ID is duplicated. If the source file is ever
replaced with a different shape, the loader and the model in
`backend/academics/models.py` must be updated together.

### After loading: the search index

The 55 prose summaries are embedded into the search index automatically by the sync
worker, within one poll cycle (~30 seconds). Confirm with:

```
docker compose logs --tail 50 sync_worker
```

You should see `embedded faculty_development_profiles id=...` lines, and afterwards
`poll cycle complete: no changes detected`.

To confirm the index actually holds them:
```
curl -s -X POST http://localhost:6333/collections/college_docs/points/count -H "Content-Type: application/json" -d "{\"filter\":{\"must\":[{\"key\":\"table\",\"match\":{\"value\":\"faculty_development_profiles\"}}]},\"exact\":true}"
```
Expect `"count":55`.

> **Note:** the 13,000 raw records are deliberately **not** embedded — they are numbers and
> categories, with no prose to search. Only the 55 summaries are. The sync worker reports
> this on startup as `excluded 2 granted table(s) with no 'updated_at' column:
> courses_prerequisites, faculty_development`, which is expected and not an error.

### Two settings this dataset required (already applied in `.env`)

Answering from retrieved text sends the model far more to read than a simple
database lookup does, and on a **CPU-only machine** that is slow enough to hit
limits that were fine before. Two settings in `.env` were changed as a result:

| Setting | Value | Why |
| --- | --- | --- |
| `OLLAMA_READ_TIMEOUT` | `240` | How long to wait for the model's first word. The built-in 120s was not enough for a retrieval question and they failed with *"The AI service is temporarily unavailable"* even though nothing was broken. Must stay **below** `GUNICORN_TIMEOUT` (300s) in production. |
| `VERIFICATION_MODEL` | `qwen2.5:3b` | The fact-checking step re-reads the whole answer *and* every retrieved passage, and cannot stream. With the 7b model it exceeded even 240s on every descriptive question, so answers were returned unverified. The smaller model (already downloaded) completes it. |

**On a machine with a GPU both of these can be reverted** — first words arrive in
seconds there. They are compensating for CPU-only inference, nothing else.

### Questions you can use to check both paths work

| Question | Should route to | Correct answer |
| --- | --- | --- |
| *How many faculty in the Engineering department have a competency level of Expert?* | SQL | 102 |
| *What is the average AI tool adoption score for Professors?* | SQL | 61.36 |
| *Give me an overview of how the Computer Science department is doing on faculty development.* | RAG | a narrative summary |
| *Which departments would you characterise as strongest at digital teaching?* | RAG | a comparative summary |

---

## Running the automated tests

### Backend (75 tests)

```bash
docker compose exec -T backend python manage.py test
```

Covers the SQL guard, the prompt-injection fencing, cross-user isolation, the
login lockout, the web-fetch allowlist and the content sanitiser. Takes about
30 seconds. Everything must pass before a deploy.

### Frontend markdown rendering (36 assertions)

`frontend/src/__markdown_test__.jsx` renders the `<Markdown>` component to
static HTML and asserts that bold, nested lists, tables, code blocks and
blockquotes all become real elements, that **no raw markdown punctuation is left
visible**, and that embedded `<script>` / `<img onerror>` are never emitted as
tags.

It is not part of `npm test` because it needs no browser and no test runner —
esbuild plus Node is the whole harness:

```bash
docker compose exec -T frontend sh -c \
  "cd /app && npx --yes esbuild src/__markdown_test__.jsx --bundle \
     --platform=node --format=cjs --outfile=/tmp/mdtest.cjs \
     --loader:.jsx=jsx --jsx=automatic --log-level=error && node /tmp/mdtest.cjs"
```

Exit code is non-zero if any assertion fails.

> The file lives in `src/` but is never shipped: nothing imports it, so the
> bundler drops it, and `.dockerignore` excludes `frontend/src/__*__.jsx` from
> the production build context. Both were verified.

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
