# Rotating secrets on a running stack

Copyright (c) 2026 Yash Garad. All rights reserved.

Ordered procedures for changing each secret without taking the assistant down
longer than necessary — or locking a service out of the database.

---

## The single most important thing on this page

**`docker compose restart` does NOT reload `.env.production`.**

`restart` stops and starts the *existing* container, which still holds the
environment it was created with. Environment variables are read when a container
is **created**, not when it is started. Editing the file and running `restart`
appears to work, changes nothing, and is the most common way a rotation silently
fails.

Always recreate:

```
docker compose --env-file .env.production -f docker-compose.yml -f docker-compose.prod.yml up -d <service>
```

Throughout this document, "restart" means that command.

### And `--env-file .env.production` is part of it

Compose resolves `${VAR}` in the compose files from `.env`, **never** from
`.env.production` — `env_file:` only injects variables into a container, it does
not feed interpolation. Omit this flag and Postgres is configured from the *old*
`.env` while the backend gets the rotated value from `.env.production`, so the
two disagree and the backend cannot authenticate.

Every command on this page includes the flag. Keep it.

---

## Which secret affects which container

| Secret | Read by | Requires a database change? | Recreate |
|---|---|---|---|
| `DJANGO_SECRET_KEY` | backend | No | `backend` |
| `POSTGRES_PASSWORD` | backend | **Yes — env var alone does nothing** | `backend` |
| `RAG_AGENT_RO_PASSWORD` | backend, sync_worker | Yes, applied automatically by backend | `backend` **then** `sync_worker` |
| `STAFF_PASSWORD` | backend | No (applied on every start) | `backend` |

---

## 1. `DJANGO_SECRET_KEY`

Simplest case: no database involvement.

1. Generate a replacement of at least 50 characters:
   ```
   openssl rand -base64 96 | tr -d '\n=+/' | cut -c1-64
   ```
2. Edit `DJANGO_SECRET_KEY` in `.env.production`.
3. Recreate the backend:
   ```
   docker compose --env-file .env.production -f docker-compose.yml -f docker-compose.prod.yml up -d backend
   ```
4. Confirm it came up: `docker compose ... logs --tail 20 backend`

**Expected side effect:** every user is logged out. The key signs session cookies,
so all existing sessions become invalid immediately. Rotate outside teaching hours.

---

## 2. `POSTGRES_PASSWORD`

**The trap:** `POSTGRES_PASSWORD` in the compose file is only consulted when
Postgres initialises an *empty* data directory. On a server with an existing
database, changing that variable has **no effect on the actual password**. You
must change it inside Postgres, or the backend will simply stop being able to
connect.

1. Change the password in the database first (the new value is prompted for, not
   typed on the command line, so it does not enter shell history):
   ```
   docker compose --env-file .env.production -f docker-compose.yml -f docker-compose.prod.yml exec postgres \
     psql -U postgres -c "\password postgres"
   ```
2. Edit `POSTGRES_PASSWORD` in `.env.production` to the same value.
3. Recreate the backend:
   ```
   docker compose --env-file .env.production -f docker-compose.yml -f docker-compose.prod.yml up -d backend
   ```
4. Verify:
   ```
   curl -sk https://<server>/api/health/
   ```
   `"database": "up"` means the backend reconnected successfully.

`sync_worker` does **not** need recreating — it connects as `rag_agent_ro`, never
as the owner.

If step 1 succeeds but step 2 is forgotten, the backend will fail its healthcheck
and `restart: always` will loop it. The logs will show a Postgres authentication
failure.

---

## 3. `RAG_AGENT_RO_PASSWORD`

**Order matters here.** The backend owns this credential: `setup_readonly_role`
runs on every backend start and issues `ALTER ROLE rag_agent_ro PASSWORD ...`
using whatever is in the environment. The sync worker only *consumes* it.

Recreating `sync_worker` first would have it authenticate with the new password
against a role that still has the old one — it will fail and restart-loop until
the backend catches up.

1. Edit `RAG_AGENT_RO_PASSWORD` in `.env.production`.
2. Recreate the **backend first** — this applies the new password to the role:
   ```
   docker compose --env-file .env.production -f docker-compose.yml -f docker-compose.prod.yml up -d backend
   ```
3. Wait for it to report healthy:
   ```
   docker compose --env-file .env.production -f docker-compose.yml -f docker-compose.prod.yml ps backend
   ```
4. Now recreate the sync worker:
   ```
   docker compose --env-file .env.production -f docker-compose.yml -f docker-compose.prod.yml up -d sync_worker
   ```
5. Verify the role still has exactly the intended privileges and no write access:
   ```
   docker compose --env-file .env.production -f docker-compose.yml -f docker-compose.prod.yml \
     exec backend python manage.py check_rag_agent_ro --check-write
   ```
   Expect `default_transaction_read_only: on`, twelve tables with `SELECT` only, and
   `INSERT correctly rejected`.
6. Confirm the worker is polling cleanly:
   ```
   docker compose --env-file .env.production -f docker-compose.yml -f docker-compose.prod.yml logs --tail 20 sync_worker
   ```

---

## 4. `STAFF_PASSWORD`

**Behaviour to be aware of:** `create_staff_user` runs on every backend start and
calls `set_password` **unconditionally**. Two consequences:

- Rotating this secret needs nothing more than an edit and a backend recreate.
- If the account's password is ever changed from inside the application, the next
  backend restart **silently reverts it** to whatever is in `.env.production`.

That second point is a real limitation of the current single-account design, and
it is what Phase 4 replaces with per-user accounts.

1. Edit `STAFF_PASSWORD` in `.env.production`.
2. Recreate the backend:
   ```
   docker compose --env-file .env.production -f docker-compose.yml -f docker-compose.prod.yml up -d backend
   ```
3. Confirm from the logs: `Updated staff user '<username>'.`

---

## Rotating everything at once

Safe order, because it never leaves a consumer ahead of its owner:

1. `\password postgres` in the database (procedure 2, step 1).
2. Edit **all four** values in `.env.production`.
3. Recreate the backend and wait for healthy:
   ```
   docker compose --env-file .env.production -f docker-compose.yml -f docker-compose.prod.yml up -d backend
   ```
4. Recreate the sync worker:
   ```
   docker compose --env-file .env.production -f docker-compose.yml -f docker-compose.prod.yml up -d sync_worker
   ```
5. Verify:
   ```
   curl -sk https://<server>/api/health/
   docker compose --env-file .env.production -f docker-compose.yml -f docker-compose.prod.yml \
     exec backend python manage.py check_rag_agent_ro --check-write
   ```

Everyone is logged out (new `DJANGO_SECRET_KEY`); no data is lost.

---

## After any rotation

- Confirm the file is still private: `ls -l .env.production` must show `-rw-------`.
- Confirm it is still untracked: `git check-ignore -q .env.production && echo ok`
- Update the institute's password manager. A rotated secret nobody recorded is an
  outage waiting for the next person who needs it.
- Never send the new value by email or chat.
