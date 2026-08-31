# Operations Walkthrough

Copyright (c) 2026 Yash Garad. All rights reserved.

Day-to-day running of the College Assistant in production: adding and removing
users, checking health, reading the audit trail, and restarting the stack.

For **first-time installation** use [DEPLOYMENT.md](DEPLOYMENT.md). For the
security posture and its limits, [SECURITY.md](SECURITY.md).

---

## The one command you need

Every production command starts with the same long prefix. Put this in
`~/.bashrc` once and the rest of this document is short:

```bash
alias dcp='docker compose --env-file .env.production -f docker-compose.yml -f docker-compose.prod.yml'
```

Both parts matter and neither is optional:

* **`-f` flags** — without them Compose loads `docker-compose.override.yml`,
  which is the *development* configuration: host source bind-mounted over the
  image, the Vite dev server, no resource limits.
* **`--env-file`** — `env_file:` in the compose file only injects variables into
  a container; it does not affect `${VAR}` interpolation, which always reads
  `.env`. Postgres takes its password by interpolation, so without this flag the
  database initialises with one password while the backend connects with
  another. See DEPLOYMENT.md → Troubleshooting.

---

## 1. The address: domain and network setup

### Internet deployment (what this system is configured for)

Pick a subdomain — `rag.college.edu` is the convention assumed throughout.

**DNS.** One `A` record pointing at the server's public IPv4 address (add an
`AAAA` record too if it has IPv6):

```
rag.college.edu.   A   203.0.113.45
```

Confirm it resolves *before* starting the stack, or the certificate request
fails:

```bash
dig +short rag.college.edu      # must print the server's public IP
```

**Firewall.** Exactly two inbound ports:

| Port | Why |
|---|---|
| **443/tcp** | The application. |
| **80/tcp** | **Required.** Let's Encrypt validates domain ownership over port 80, and Caddy redirects it to HTTPS. Blocking it means no certificate — and no renewal in 60 days. |

Nothing else. Postgres (5432), Qdrant (6333) and the backend (8000) are bound to
`127.0.0.1` and are not reachable from the network.

```bash
sudo ufw allow 80/tcp && sudo ufw allow 443/tcp && sudo ufw enable
```

**Configuration** in `.env.production`:

```
SERVER_HOST=rag.college.edu
DJANGO_ALLOWED_HOSTS=rag.college.edu
DJANGO_CSRF_TRUSTED_ORIGINS=https://rag.college.edu
CADDY_TLS=
```

`CADDY_TLS` **empty** is what selects a real certificate. Caddy obtains it on
first start and renews it automatically forever — no certbot, no cron job, no
reload hook. Confirm it worked:

```bash
dcp logs caddy | grep -i "certificate obtained"
curl -sI https://rag.college.edu/ | head -1        # HTTP/2 200, no -k needed
```

If `curl` needs `-k`, you are on a self-signed certificate — check `CADDY_TLS`
is empty and that port 80 is open.

**Once the real certificate is confirmed working, turn on HSTS** — and not
before. HSTS makes certificate warnings non-bypassable, which is what you want
with a real certificate and a lockout with a self-signed one. Ramp it:

```
# Caddy's value is the one the browser actually sees: it sets this header on
# every response and REPLACES Django's. Setting only DJANGO_HSTS_SECONDS leaves
# max-age=0 on the wire, which tells browsers to forget any pin they hold.
CADDY_HSTS_MAX_AGE=3600      # then 86400, then 31536000
DJANGO_HSTS_SECONDS=3600     # keep in step with the line above
```

### LAN-only alternative

If there is no public DNS name, set `CADDY_TLS="tls internal"` and
`SERVER_HOST` to the server's LAN IP. Caddy then issues a self-signed
certificate, and **every browser warns until its CA is installed on each client
machine**:

```bash
dcp cp caddy:/data/caddy/pki/authorities/local/root.crt ./college-assistant-ca.crt
```

Distribute that file and install it as a trusted root on each machine. Leave
**both** `CADDY_HSTS_MAX_AGE=0` and `DJANGO_HSTS_SECONDS=0` until that is done
everywhere — Caddy's is the value browsers act on, so leaving it at 0 is what
actually keeps the lockout risk away.

> Self-signed certificates on an internet-facing service are **not**
> appropriate: they train users to click through security warnings, which is the
> habit an attacker relies on.

---

## 2. Adding and removing users

### Add one person

```bash
dcp exec backend python manage.py create_user jsmith \
    --role staff --full-name "J Smith" --created-by "registrar"
```

Prints one initial password. There is deliberately no option to choose it — the
command always generates a strong random one. Give it to its owner over a
channel you trust, then clear your screen.

The account **must change that password at first login** and cannot ask the
assistant anything until it does.

`--role` is `staff` or `student`.

### Add many people at once

Production containers have no bind mounts, so a CSV on the host is not visible
inside the container and must be copied in.

`roster.csv`:
```
username,role,email,full_name
2021CS001,student,2021cs001@college.edu,Anita Rao
jsmith,staff,jsmith@college.edu,J Smith
```

```bash
dcp cp roster.csv backend:/tmp/roster.csv
dcp exec backend python manage.py import_users /tmp/roster.csv --dry-run   # always first
dcp exec backend python manage.py import_users /tmp/roster.csv --created-by "registrar"
dcp cp backend:/tmp/roster.csv.credentials.csv ./roster.csv.credentials.csv
dcp exec backend rm -f /tmp/roster.csv /tmp/roster.csv.credentials.csv
```

The import is **all-or-nothing** — one bad row creates no accounts at all.
Passwords go to `roster.csv.credentials.csv` (mode 600) and are never printed.
**Shred it once distributed:** `shred -u roster.csv.credentials.csv`.

### Remove someone

```bash
dcp exec backend python manage.py disable_user jsmith
```

Disabling, not deleting — their audit trail must survive their departure.

### Someone forgot their password

```bash
dcp exec backend python manage.py reset_password jsmith
```

Generates a new random password, forces a change at next login, and ends their
existing sessions. There is no email-based reset: this deployment may have no
outbound mail, and an email reset would move every account's security onto
whatever mailbox is on file.

### Someone is locked out

After **5 failed attempts** an account locks for **15 minutes**. It clears
itself — no action needed. To clear it immediately, `reset_password` also
resets the counter.

To see who is locked:

```bash
dcp exec backend python manage.py shell -c "
from accounts.models import UserProfile
from django.utils import timezone
for p in UserProfile.objects.filter(locked_until__gt=timezone.now()):
    print(p.user.username, 'locked until', p.locked_until)"
```

### List everyone

```bash
dcp exec backend python manage.py shell -c "
from django.contrib.auth.models import User
for u in User.objects.order_by('username'):
    print(f'{u.username:24} active={u.is_active} staff={u.is_staff} last_login={u.last_login}')"
```

---

## 3. Checking system health

### There are exactly THREE health URLs. There is no `/ready/`.

Getting this wrong wastes an outage. During resilience testing a check script
probed `/api/health/ready/` — which has never existed — and separately called
`.json()` on the HTML status page. Both failed, and the report read "health
endpoint: HTTP None" through four consecutive tests, which looked exactly like
the health system itself being down. It was not.

| URL | Returns | Use it for |
|---|---|---|
| `/api/health/live/` | JSON, always 200 while the process is up | Liveness only. Deliberately checks **no** dependencies, so an Ollama outage never marks the backend itself unhealthy. This is what the container healthcheck uses. |
| `/api/health/` | JSON, **200 all up / 503 any down**, with a per-service breakdown | Monitoring, scripts, uptime checks. |
| `/api/health/status/` | **HTML**, 200 all up / 503 any down | A person, in a browser. Not parseable as JSON — do not try. |

Anything else 404s, and a 404 from the SPA catch-all looks like a page rather
than an error, which is how the wrong path went unnoticed.

### The status page — start here

**`https://rag.college.edu/api/health/status/`**

A plain page listing every component, refreshing every 15 seconds, telling you
which one is down and what to do about it. It needs no login, deliberately: the
people who need it are locked out precisely when authentication is what broke.

It returns HTTP **503** when anything is down, so an external uptime monitor can
watch that URL directly.

### Machine-readable

```bash
curl -s https://rag.college.edu/api/health/ | jq
# {"status":"ok","services":{"database":"up","sessions":"up","llm":"up","vector_store":"up"}}
```

### What each component failing actually looks like

The two most confusable rows are **Database** and **Sessions & sign-in**, because
they fail in opposite directions:

| Down | What users see | What still works |
|---|---|---|
| **Database** (Postgres) | New sign-ins fail with "sign-in is temporarily unavailable". Answers lose their records lookup and say so. | **Anyone already signed in keeps working.** Sessions are in Redis, not Postgres. |
| **Sessions & sign-in** (Redis) | *Everyone* is signed out at once, and nobody can sign back in. | Nothing user-facing. |

"Everybody got logged out" therefore points at **Redis**, not at the database —
which is the whole reason it has its own row rather than being folded into one
"storage" line.

### Are the containers up?

```bash
dcp ps
```

Every row should read `running` or `healthy`. `ollama-pull` showing `exited (0)`
is correct — it is a one-shot model downloader, not a service.

### The full pre-flight check

```bash
sh scripts/verify_deployment.sh
```

Interrogates the running system: DEBUG off, gunicorn serving, frontend is a
built bundle, no default secrets, `rag_agent_ro` cannot write, backups fresh,
healthchecks passing. Exit code is the number of failures. **Run it after every
deploy.**

---

## 4. Reading the audit trail

There are **three** separate records, and the difference matters.

| Table | What it is | Who may delete it |
|---|---|---|
| `audit_log` | Compliance record of every question | Nobody; purged on retention schedule |
| `web_fetch_log` | Every external page fetch, including refusals | Nobody |
| `conversation` | A user's own chat history, for their convenience | The user |

A user deleting their conversation does **not** touch the audit log. That
separation is deliberate.

### Recent activity

```bash
dcp exec -T postgres psql -U postgres -d college_rag -c "
SELECT created_at, username, client_ip, left(question, 60) AS question, route
FROM audit_log ORDER BY created_at DESC LIMIT 20;"
```

### Everything one person asked

```bash
dcp exec -T postgres psql -U postgres -d college_rag -c "
SELECT created_at, question, left(final_answer, 80) AS answer
FROM audit_log WHERE username = 'jsmith' ORDER BY created_at DESC;"
```

### Export a date range for an investigation

```bash
dcp exec -T postgres psql -U postgres -d college_rag \
  --csv -c "SELECT * FROM audit_log
            WHERE created_at >= '2026-08-01' AND created_at < '2026-09-01'" \
  > audit-2026-08.csv
```

> **Handle that file as personal data.** Each row holds a username, an IP
> address, the question text, the **full answer**, and the **generated SQL** —
> and `generated_sql` shows the exact `WHERE` clause, so it reveals who or what
> someone was looking up. Store it as you would any student record and delete it
> when the investigation closes.

### External fetches, especially refusals

```bash
dcp exec -T postgres psql -U postgres -d college_rag -c "
SELECT created_at, outcome, url, detail FROM web_fetch_log
WHERE outcome = 'refused' ORDER BY created_at DESC LIMIT 20;"
```

A run of refusals means something is trying to point the fetcher at a URL that
is not on the allowlist. Worth looking at.

### Retention

Audit rows are kept `AUDIT_LOG_RETENTION_DAYS` (default 90), then purged:

```bash
dcp exec backend python manage.py purge_audit_log --dry-run
dcp exec backend python manage.py purge_audit_log
```

**Retention only exists if this is scheduled.** Confirm the cron entry:

```bash
crontab -l | grep purge_audit_log
```

---

## 5. Restarting

### One service

```bash
dcp restart backend
```

### The whole stack

```bash
dcp restart
```

Takes about 30 seconds. **The first question afterwards will be slow** (a minute
or more) while the language model loads back into memory; every question after
that is normal.

### After changing `.env.production`

`restart` does **not** reload environment variables — a container keeps the
environment it was *created* with. You must recreate:

```bash
dcp up -d
```

This is the single most common way a configuration change appears to do nothing.

### Stopping

```bash
dcp down          # stops everything, keeps all data
dcp up -d         # brings it back
```

> Never add `-v` unless you intend to **erase the database, chat history and
> downloaded models**.

### If a service will not come back

```bash
dcp logs --tail 100 backend
```

The backend refuses to start on unsafe configuration, and says which value is
wrong — that is correct behaviour, not a fault. DEPLOYMENT.md lists each message
and its fix.

---

## 6. Backups

```bash
sh scripts/backup.sh
```

Postgres dump plus a Qdrant snapshot, timestamped, with a SHA-256 manifest,
pruned after 14 days.

**Backups land on the same disk as the database, which does not protect you from
that disk failing.** Copy them elsewhere:

```bash
scp -r ./backups/<timestamp> backup-host:/srv/college-assistant-backups/
```

**A backup you have never restored from is not a backup.** Rehearse into a
scratch database — the live one is untouched:

```bash
sh scripts/restore.sh --dry-run ./backups/<timestamp>
sh scripts/restore.sh ./backups/<timestamp>
```

---

## Quick reference

| Task | Command |
|---|---|
| Status page (HTML, for a person) | `https://rag.college.edu/api/health/status/` |
| Health JSON (for monitoring) | `curl -s https://.../api/health/` |
| Liveness only (no dependencies) | `curl -s https://.../api/health/live/` |
| Containers | `dcp ps` |
| Everyone logged out? | `dcp restart redis` — sessions live there, not in Postgres |
| Full check | `sh scripts/verify_deployment.sh` |
| Add user | `dcp exec backend python manage.py create_user <name> --role staff` |
| Reset password | `dcp exec backend python manage.py reset_password <name>` |
| Disable user | `dcp exec backend python manage.py disable_user <name>` |
| Restart all | `dcp restart` |
| Apply config change | `dcp up -d` |
| Logs | `dcp logs -f backend` |
| Backup | `sh scripts/backup.sh` |

---

## A note on the language model

This system runs **Ollama**, not vLLM. vLLM requires an NVIDIA GPU, and on a
CPU-only server its continuous batching gives nothing: one 7B generation already
saturates every core, so batching concurrent requests makes them all slower
rather than faster.

The practical consequence is capacity: roughly **2–3 people asking at a
leisurely pace**, with repeated questions served instantly from cache. See
[docs/SCALING.md](docs/SCALING.md) for the measurements. If the institute adds a
GPU, that document has the migration path.
