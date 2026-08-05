# College Assistant

An offline AI assistant that answers questions about a college's database — courses,
departments, faculty, fees, schedules, and more — through a simple chat website. Everything
runs on your own server; no data leaves the machine.

This guide is written for someone with **no coding background**. If you can install a program
and copy-paste a few lines into a terminal, you can run this.

> **Already installed?** For everyday running — starting, health checks, logs, and
> troubleshooting — use the one-page [RUNBOOK.md](RUNBOOK.md) instead of this file.
>
> **Deploying on a real college server?** This guide sets up a *development*
> stack: debug mode on, example passwords, and Django's development web server.
> Use [DEPLOYMENT.md](DEPLOYMENT.md) instead — it is the production path, and it
> covers the pre-flight checklist you must complete before students get the address.

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
