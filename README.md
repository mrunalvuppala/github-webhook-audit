# AgentAuditAI

**GitHub webhook gateway that asynchronously scans code diffs for leaked credentials.**

Built for compliance-focused teams who need fast webhook verification, background auditing, and zero retention of sensitive diff content.

---

## What it does

```mermaid
flowchart LR
    GH[GitHub Webhook] --> API[FastAPI Gateway]
    API -->|HMAC Verify| API
    API -->|202 Accepted| GH
    API -->|Queue Task| Redis[(Redis)]
    Redis --> Worker[Celery Worker]
    Worker --> Engine[Stateless Audit Engine]
    Engine --> DB[(Metadata Store)]
```

1. **GitHub** sends a signed webhook to `/v1/webhooks/github`
2. **FastAPI** verifies the HMAC signature and immediately returns `202 Accepted`
3. **Celery worker** scans the diff for AWS, Stripe, and GitLab secrets
4. **Only metadata** is logged and stored — never the raw code

---

## Clone and run (for anyone using the GitHub repo)

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running
- [Git](https://git-scm.com/downloads)

### Step 1 — Clone the repository

```bash
git clone https://github.com/mrunalvuppala/github-webhook-audit.git
cd github-webhook-audit
```

### Step 2 — Configure environment

**Windows (PowerShell / CMD):**
```bash
copy .env.example .env
```

**macOS / Linux:**
```bash
cp .env.example .env
```

Edit `.env` if needed. Defaults work for local development.

### Step 3 — Start the stack

```bash
docker compose up --build -d
```

Wait ~10 seconds, then verify:

```bash
curl http://localhost:8000/health
```

Expected response: `{"status":"ok","service":"AgentAuditAI"}`

### Step 4 — Open the app

| What | URL |
|---|---|
| Demo UI | [http://localhost:8000](http://localhost:8000) |
| API docs | [http://localhost:8000/docs](http://localhost:8000/docs) |
| Health check | [http://localhost:8000/health](http://localhost:8000/health) |
| AST / secret scan | `POST /v1/scan` |

### Step 5 — Run tests (optional)

```bash
python scripts/test_scan_engine.py
```

### Step 6 — Install pre-commit hook (optional)

Scans staged files before each commit. Requires **Git Bash** or **WSL** on Windows:

```bash
./install.sh
```

Set these in `.env` or your shell if the API is not on localhost:

```env
AGENTAUDIT_API_URL=http://localhost:8000/v1/scan
AGENTAUDIT_OFFLINE_MODE=block
AGENTAUDIT_TIMEOUT=10
```

### Stop the stack

```bash
docker compose down
```

---

## Run locally on your machine (Windows)

If you already have the repo at `C:\git\github-webhook-audit`:

1. **Start Docker Desktop** (must be running).
2. Open PowerShell in the project folder:
   ```powershell
   cd C:\git\github-webhook-audit
   copy .env.example .env
   docker compose up --build -d
   ```
3. **Verify** — open [http://localhost:8000/health](http://localhost:8000/health) or run:
   ```powershell
   python scripts\test_scan_engine.py
   ```
4. **Demo UI** — open [http://localhost:8000](http://localhost:8000) or double-click `start.bat`.
5. **Pre-commit** (optional) — in Git Bash: `./install.sh`

**Restart after code changes:**
```powershell
docker compose up --build -d
```
Or double-click `restart.bat`.

---

## Easiest way to run (for presentations)

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running

### Step 1 — Start everything (one double-click)

```
start.bat
```

Or from terminal:

```bash
docker compose up --build
```

### Step 2 — Open the demo UI (best for presentations)

[http://localhost:8000](http://localhost:8000)

Click the example buttons, then **Run audit** for instant PASS/FAIL results in the browser.

Or use the API docs:

[http://localhost:8000/docs](http://localhost:8000/docs)

### Step 3 — Run the live demo

Double-click:

```
demo.bat
```

Or:

```bash
python scripts/demo.py
```

The demo sends 3 webhook scenarios and shows HTTP responses. Audit results appear in the **worker** terminal.

---

## Presentation cheat sheet

| What to show | URL / Command |
|---|---|
| **Demo UI dashboard** | [http://localhost:8000](http://localhost:8000) |
| Interactive API docs | [http://localhost:8000/docs](http://localhost:8000/docs) |
| Health check | [http://localhost:8000/health](http://localhost:8000/health) |
| Webhook endpoint | `POST /v1/webhooks/github` |
| Live demo script | `demo.bat` |
| Worker audit logs | Docker terminal for `worker` service |

### Talking points

- **Security first** — HMAC-SHA256 verification before any processing
- **Fast response** — GitHub gets `202` immediately; audit runs in background
- **Compliance** — diff content is never logged, stored, or retained in memory
- **Detects** — AWS keys, Stripe secrets, GitLab tokens

---

## Manual setup (without Docker)

```bash
cd C:\git\github-webhook-audit
pip install -r requirements.txt
copy .env.example .env
```

**Terminal 1 — Redis:**
```bash
docker run -d -p 6379:6379 redis:alpine
```

**Terminal 2 — Worker:**
```bash
python -m celery -A app.workers.tasks.celery_app worker --loglevel=info --pool=solo
```

**Terminal 3 — API:**
```bash
python -m uvicorn app.main:app --reload --port 8000
```

---

## Configuration

Copy `.env.example` to `.env`:

```env
GITHUB_WEBHOOK_SECRET=replace-with-your-webhook-secret
DATABASE_URL=postgresql://user:password@localhost:5432/tenant_cache
REDIS_URL=redis://localhost:6379/0
ENVIRONMENT=development

# Pre-commit client
AGENTAUDIT_API_URL=http://localhost:8000/v1/scan
AGENTAUDIT_OFFLINE_MODE=block
AGENTAUDIT_TIMEOUT=10
```

---

## Project structure

```
app/
├── core/config.py           # Environment configuration
├── schemas/scan.py          # Scan API request/response models
├── services/
│   ├── audit_engine.py      # Webhook diff credential scanner
│   └── scan_engine.py       # AST + secret scan engine
├── workers/tasks.py         # Celery background tasks
├── static/index.html        # Demo UI dashboard
└── main.py                  # FastAPI gateway
agentaudit/client.py         # Pre-commit scan client
hooks/pre-commit             # Git hook wrapper
install.sh                   # Pre-commit installer
scripts/test_scan_engine.py  # Scan engine tests
docker-compose.yml           # One-command startup
start.bat                    # Double-click to run
demo.bat                     # Double-click to demo
```

---

## Documentation

Full technical and enterprise integration guide:

- **[docs/PROJECT_DOCUMENTATION.md](docs/PROJECT_DOCUMENTATION.md)** — architecture, testing, enterprise & public company integration
- Double-click **`download-docs.bat`** to copy the document to your Desktop

---

## GitHub repo

[github.com/mrunalvuppala/github-webhook-audit](https://github.com/mrunalvuppala/github-webhook-audit)
