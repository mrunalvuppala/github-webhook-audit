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

### Step 2 — Open the API docs (great for demos)

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
```

---

## Project structure

```
app/
├── core/config.py          # Environment configuration
├── services/audit_engine.py # Credential scanner
├── workers/tasks.py         # Celery background tasks
└── main.py                  # FastAPI webhook gateway
scripts/demo.py              # Live presentation demo
docker-compose.yml           # One-command startup
start.bat                    # Double-click to run
demo.bat                     # Double-click to demo
```

---

## GitHub repo

[github.com/mrunalvuppala/github-webhook-audit](https://github.com/mrunalvuppala/github-webhook-audit)
