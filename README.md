# AgentAudit AI — Multi-Tenant Infrastructure

**Production-grade, multi-tenant GitHub webhook security auditing platform with PostgreSQL Row-Level Security, Redis-backed Celery workers, and AST/secret scanning.**

> **Architecture designed, engineered, and maintained by Naga Sai Mrunal Vuppala.**

---

## System Topology

```
                         INTERNET / GITHUB
                                 |
                                 |  HTTPS POST (signed payload)
                                 v
+---------------------------------------------------------------------+
|                        DOCKER COMPOSE HOST                          |
|                                                                     |
|   +-------------------+       +-------------------+                   |
|   |   GITHUB APP /    |       |   DEVELOPER CLI   |                   |
|   |   WEBHOOK SOURCE  |       |   curl / pre-commit|                  |
|   +---------+---------+       +---------+---------+                   |
|             |                           |                           |
|             | X-Hub-Signature-256       | /v1/scan                  |
|             v                           v                           |
|   +-------------------------------------------------------------+   |
|   |                    FASTAPI WEB SERVICE (:8000)              |   |
|   |  +-------------------------------------------------------+  |   |
|   |  | Latency Telemetry Middleware (X-Process-Time-Ms)      |  |   |
|   |  +-------------------------------------------------------+  |   |
|   |  | POST /v1/webhooks/github                              |  |   |
|   |  |   1. Read raw body                                    |  |   |
|   |  |   2. HMAC-SHA256 constant-time verify                 |  |   |
|   |  |   3. Parse installation_id                            |  |   |
|   |  |   4. celery.delay()  -----------+                     |  |   |
|   |  |   5. Return 202 Accepted (<50ms)|                     |  |   |
|   |  +---------------------------------|---------------------+  |   |
|   +------------------------------------|------------------------+   |
|                                        |                            |
|                                        | task JSON envelope         |
|                                        v                            |
|                          +-------------------------+                |
|                          |   REDIS BROKER (:6379)  |                |
|                          |   Celery queue + results|                |
|                          +------------+------------+                |
|                                       |                             |
|                                       | BRPOP / task dispatch         |
|                                       v                             |
|   +-------------------------------------------------------------+   |
|   |                  CELERY WORKER POOL                         |   |
|   |  +-------------------------------------------------------+  |   |
|   |  | process_github_webhook_audit                          |  |   |
|   |  |   1. Resolve / create Organization                    |  |   |
|   |  |   2. SET LOCAL app.current_organization_id = :org_id  |  |   |
|   |  |   3. SecurityEngine.scan_diff()                       |  |   |
|   |  |   4. INSERT scan_audit_logs (RLS enforced)            |  |   |
|   |  +-------------------------------------------------------+  |   |
|   +-----------------------------|-------------------------------+   |
|                                 |                                   |
|                                 | SQL (tenant-scoped session)       |
|                                 v                                   |
|                    +---------------------------+                    |
|                    |  POSTGRESQL 16 (:5432)    |                    |
|                    |  organizations            |                    |
|                    |  scan_audit_logs + RLS    |                    |
|                    +---------------------------+                    |
+---------------------------------------------------------------------+
```

### Request lifecycle summary

| Stage | Component | Action | Target latency |
|---|---|---|---|
| 1 | GitHub | Delivers signed webhook | — |
| 2 | FastAPI `web` | HMAC verify + enqueue | < 50 ms |
| 3 | Redis | Stores Celery task | < 5 ms |
| 4 | Celery `worker` | Scan diff + persist metadata | async |
| 5 | PostgreSQL | Tenant-isolated audit log row | async |

---

## Database Isolation — PostgreSQL RLS

AgentAudit AI enforces **multi-tenant isolation** at the database layer using PostgreSQL Row-Level Security (RLS) on `scan_audit_logs`.

### Runtime tenant binding

Before any mutation or read against `scan_audit_logs`, the Celery worker executes:

```sql
SET LOCAL app.current_organization_id = '<organization-uuid>';
```

`SET LOCAL` scopes the setting to the current transaction, preventing cross-tenant leakage between pooled connections.

### RLS policy

```sql
ALTER TABLE scan_audit_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE scan_audit_logs FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_policy ON scan_audit_logs
USING (organization_id = current_setting('app.current_organization_id', true)::uuid);
```

### Schema mapping

| Table | Column | Type | Purpose |
|---|---|---|---|
| `organizations` | `id` | `UUID` PK | Canonical tenant identifier |
| `organizations` | `org_name` | `VARCHAR(255)` | GitHub org / account display name |
| `organizations` | `github_installation_id` | `VARCHAR(64)` UNIQUE | Maps GitHub App installation to tenant |
| `organizations` | `author_metadata` | `JSONB` | Default `{"creator": "Naga Sai Mrunal Vuppala"}` |
| `organizations` | `created_at` | `TIMESTAMPTZ` | Tenant provisioning timestamp |
| `scan_audit_logs` | `id` | `UUID` PK | Immutable audit record identifier |
| `scan_audit_logs` | `organization_id` | `UUID` FK (indexed) | **RLS isolation key** |
| `scan_audit_logs` | `repository_name` | `VARCHAR(512)` | `owner/repo` from webhook payload |
| `scan_audit_logs` | `pull_request_number` | `INTEGER` | PR number when applicable |
| `scan_audit_logs` | `commit_sha` | `VARCHAR(64)` | Commit SHA when applicable |
| `scan_audit_logs` | `scan_status` | `VARCHAR(32)` | `passed` or `blocked` |
| `scan_audit_logs` | `vulnerabilities_found` | `JSONB` | Structured secret/AST findings |
| `scan_audit_logs` | `metadata_summary` | `JSONB` | Violation counts, event metadata |
| `scan_audit_logs` | `author_metadata` | `JSONB` | Default `{"creator": "Naga Sai Mrunal Vuppala"}` |
| `scan_audit_logs` | `created_at` | `TIMESTAMPTZ` | Audit timestamp |

### RLS evaluation flow

| Step | Actor | Operation | RLS outcome |
|---|---|---|---|
| 1 | Celery worker | `SET LOCAL app.current_organization_id` | Binds session to tenant UUID |
| 2 | PostgreSQL | Evaluates `USING` clause on `SELECT` | Returns only matching `organization_id` rows |
| 3 | PostgreSQL | Evaluates policy on `INSERT` | Permits writes only when `organization_id` matches setting |
| 4 | Other tenants | Attempt cross-tenant `SELECT` | **Zero rows returned** (silent isolation) |

---

## Local Deployment Runbook

### Prerequisites

- Docker Desktop (or Docker Engine + Compose v2)
- Git
- Python 3.12+ (optional, for local script tests outside containers)

### 1. Clone and configure

```bash
git clone https://github.com/mrunalvuppala/github-webhook-audit.git
cd github-webhook-audit
cp .env.example .env    # Windows: copy .env.example .env
```

### 2. Build and start the four-service stack

```bash
docker-compose up --build -d
```

Services started:

| Service | Image / build | Port | Role |
|---|---|---|---|
| `postgres` | `postgres:16-alpine` | 5432 | Multi-tenant metadata store |
| `redis` | `redis:alpine` | 6379 | Celery broker + result backend |
| `web` | project `Dockerfile` | 8000 | FastAPI ingress |
| `worker` | project `Dockerfile` | — | Celery audit processor |

### 3. Verify service health

```bash
docker-compose ps
curl http://localhost:8000/health
```

Expected health response:

```json
{
  "status": "ok",
  "service": "AgentAuditAI",
  "database": "connected",
  "redis": "connected",
  "environment": "development"
}
```

### 4. Inspect live logs

```bash
docker-compose logs web --tail 50
docker-compose logs worker --tail 50
docker-compose logs postgres --tail 20
docker-compose logs redis --tail 20
```

Follow logs in real time:

```bash
docker-compose logs -f web worker
```

### 5. Run scan engine validation

```bash
pip install -r requirements.txt
python scripts/test_scan_engine.py
```

### 6. Stop the stack

```bash
docker-compose down
```

Persisted PostgreSQL data survives in the `postgres_data` volume until removed:

```bash
docker-compose down -v
```

---

## API Testing Suite

Set your webhook secret (must match `.env`):

```bash
export GITHUB_WEBHOOK_SECRET="replace-with-your-webhook-secret"
```

### Health probe

```bash
curl -s http://localhost:8000/health | python -m json.tool
```

### Synchronous scan endpoint

```bash
curl -s -X POST http://localhost:8000/v1/scan \
  -H "Content-Type: application/json" \
  -d '{
    "files": [
      {"path": "unsafe.py", "content": "result = eval(user_input)\n"}
    ]
  }' | python -m json.tool
```

### Signed GitHub webhook (async pipeline)

**Linux / macOS / Git Bash:**

```bash
BODY='{"installation":{"id":4242,"account":{"login":"acme-corp"}},"repository":{"full_name":"acme-corp/payments"},"pull_request":{"number":17},"after":"abc123def456","diff":"+API_KEY = \"AKIAIOSFODNN7EXAMPLE\"\n"}'
SIG="sha256=$(printf '%s' "$BODY" | openssl dgst -sha256 -hmac "$GITHUB_WEBHOOK_SECRET" | awk '{print $2}')"

curl -i -X POST http://localhost:8000/v1/webhooks/github \
  -H "Content-Type: application/json" \
  -H "X-Hub-Signature-256: $SIG" \
  -d "$BODY"
```

**PowerShell:**

```powershell
$secret = "replace-with-your-webhook-secret"
$body = '{"installation":{"id":4242,"account":{"login":"acme-corp"}},"repository":{"full_name":"acme-corp/payments"},"pull_request":{"number":17},"after":"abc123def456","diff":"+API_KEY = \"AKIAIOSFODNN7EXAMPLE\"\n"}'
$hmac = New-Object System.Security.Cryptography.HMACSHA256
$hmac.Key = [Text.Encoding]::UTF8.GetBytes($secret)
$hash = $hmac.ComputeHash([Text.Encoding]::UTF8.GetBytes($body))
$sig = "sha256=" + (-join ($hash | ForEach-Object { $_.ToString("x2") }))
Invoke-WebRequest -Uri "http://localhost:8000/v1/webhooks/github" -Method POST `
  -Headers @{"X-Hub-Signature-256"=$sig; "Content-Type"="application/json"} `
  -Body $body
```

Expected response: **HTTP 202 Accepted** with `X-Process-Time-Ms` header.

Confirm worker processing:

```bash
docker-compose logs worker --tail 30
```

### Development demo webhook (no signature required)

```bash
curl -s -X POST http://localhost:8000/v1/demo/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "installation_id": "4242",
    "repository_name": "acme-corp/payments",
    "pull_request_number": 17,
    "commit_sha": "abc123def456",
    "diff": "+stripe_key = \"sk_live_abcdefghijklmnopqrstuv\"\n"
  }' | python -m json.tool
```

---

## Configuration reference

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `DATABASE_URL` | Yes | — | PostgreSQL connection string |
| `REDIS_URL` | Yes | `redis://localhost:6379/0` | Celery broker/backend |
| `GITHUB_WEBHOOK_SECRET` | Yes | — | HMAC signing secret for GitHub webhooks |
| `SECRET_KEY` | Yes | — | Application cryptographic secret |
| `SECURITY_ENVIRONMENT` | No | `development` | `development` enables demo endpoints |

---

## Project structure

```
.
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── README.md
├── LICENSE
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── models.py
│   ├── schemas.py
│   ├── tasks.py
│   └── services/
│       ├── __init__.py
│       ├── ast_parser.py
│       └── security_engine.py
└── alembic/
    └── env.py
```

---

## Documentation

- **[docs/PROJECT_DOCUMENTATION.md](docs/PROJECT_DOCUMENTATION.md)** — full technical guide, architecture, RLS, enterprise integration
- Run `python scripts/generate_word_doc.py` for Word documentation with diagrams
- Double-click **`download-docs.bat`** or **`download-word-doc.bat`** to copy docs to Desktop

---

## License

Licensed under the **Business Source License 1.1** by **Naga Sai Mrunal Vuppala (Founder, AgentAudit AI)**.

- **Change Date:** 2029-07-10
- **Change License:** Apache License, Version 2.0
- **Additional Use Grant:** Competing commercial cloud multi-tenant SaaS deployments are prohibited.

See [LICENSE](LICENSE) for full terms.

---

## Architectural Credit

**Architecture designed, engineered, and maintained by Naga Sai Mrunal Vuppala.**
