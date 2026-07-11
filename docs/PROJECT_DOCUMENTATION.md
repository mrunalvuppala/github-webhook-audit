# AgentAudit AI — Complete Project & Technical Documentation

**Version:** 2.0.0  
**Author:** Naga Sai Mrunal Vuppala ([@mrunalvuppala](https://github.com/mrunalvuppala))  
**Repository:** [github.com/mrunalvuppala/github-webhook-audit](https://github.com/mrunalvuppala/github-webhook-audit)  
**Last Updated:** July 2026

> **Architecture designed, engineered, and maintained by Naga Sai Mrunal Vuppala.**

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [System Architecture](#2-system-architecture)
3. [Component Reference](#3-component-reference)
4. [Database & Multi-Tenant Isolation](#4-database--multi-tenant-isolation)
5. [Security & Compliance Design](#5-security--compliance-design)
6. [Installation & Operations](#6-installation--operations)
7. [Testing Guide](#7-testing-guide)
8. [Enterprise Integration](#8-enterprise-integration)
9. [Public Company Integration](#9-public-company-integration)
10. [API Reference](#10-api-reference)
11. [Troubleshooting](#11-troubleshooting)
12. [Roadmap & Extensions](#12-roadmap--extensions)
13. [Technology Stack & Rationale](#13-technology-stack--rationale)

---

## 1. Executive Summary

**AgentAudit AI** is a production-grade, multi-tenant GitHub webhook security platform. It verifies signed webhook events, queues asynchronous security scans, persists tenant-isolated audit metadata in PostgreSQL, and returns immediate `202 Accepted` responses to GitHub.

### Key capabilities

| Capability | Description |
|---|---|
| Webhook verification | HMAC-SHA256 constant-time validation via `X-Hub-Signature-256` |
| Asynchronous processing | Celery workers backed by Redis |
| Secret detection | AWS, Stripe, GitLab, and generic API token patterns |
| AST validation | Dangerous `eval()`, `exec()`, `os.system()`, `subprocess.*` calls |
| Multi-tenant persistence | PostgreSQL with Row-Level Security (RLS) on audit logs |
| Demo UI | Browser dashboard for live PASS/FAIL demonstrations |
| Pre-commit client | Optional git hook scanning staged files via `/v1/scan` |

### Technology stack

| Layer | Technology |
|---|---|
| API Gateway | FastAPI + Uvicorn |
| Configuration | Pydantic Settings v2 (`app/config.py`) |
| Task Queue | Celery + Redis |
| Database | PostgreSQL 16 + SQLAlchemy 2.0 |
| Scan Engine | `SecurityEngine` + `ASTParser` (tree-sitter + regex) |
| Migrations | Alembic |
| Deployment | Docker Compose (4 services) |
| License | Business Source License 1.1 |

---

## 2. System Architecture

### High-level topology

```
GitHub Webhook ──► FastAPI Web (:8000)
                      │ HMAC verify
                      │ Return 202 (<50ms)
                      ▼
                   Redis (:6379)
                      │
                      ▼
                 Celery Worker
                      │ SET LOCAL tenant context
                      │ SecurityEngine.scan_diff()
                      ▼
              PostgreSQL (:5432)
              organizations + scan_audit_logs (RLS)
```

### Mermaid data flow

```mermaid
flowchart TB
    subgraph External
        GH[GitHub / GitHub Enterprise]
        CLI[Developer CLI / Pre-commit]
    end

    subgraph Gateway["FastAPI Web Service"]
        WH["POST /v1/webhooks/github"]
        SCAN["POST /v1/scan"]
        DEMO["POST /v1/demo/audit"]
        HMAC[HMAC-SHA256 Verify]
    end

    subgraph Queue["Message Broker"]
        REDIS[(Redis)]
    end

    subgraph Workers["Background Processing"]
        CELERY[Celery Worker]
        ENGINE[SecurityEngine + ASTParser]
        RLS[SET LOCAL tenant context]
    end

    subgraph Storage["PostgreSQL"]
        ORG[(organizations)]
        LOGS[(scan_audit_logs + RLS)]
    end

    subgraph DemoUI["Browser Dashboard"]
        UI["GET /"]
    end

    GH -->|Signed webhook| WH
    CLI --> SCAN
    WH --> HMAC
    HMAC -->|403 if invalid| GH
    HMAC -->|202 Accepted| GH
    HMAC -->|delay()| REDIS
    REDIS --> CELERY
    CELERY --> ENGINE
    CELERY --> RLS
    RLS --> LOGS
    CELERY --> ORG
    UI --> DEMO
    DEMO --> ENGINE
```

### Production webhook lifecycle

1. GitHub delivers `POST /v1/webhooks/github` with raw JSON body.
2. Gateway reads **raw bytes** to preserve signature integrity.
3. `GITHUB_WEBHOOK_SECRET` computes expected `sha256=` digest.
4. `hmac.compare_digest` performs constant-time comparison.
5. On success, `installation.id` is extracted from the payload.
6. `process_github_webhook_audit.delay()` enqueues the job on the `agentaudit` Celery queue.
7. Gateway returns **HTTP 202 Accepted** immediately.
8. Worker resolves or creates an `Organization` record.
9. Worker executes `SET LOCAL app.current_organization_id` for RLS.
10. `SecurityEngine.scan_diff()` inspects added diff lines.
11. A `ScanAuditLog` row is inserted under tenant isolation.
12. Diff content is purged from memory; only metadata is retained.

---

## 3. Component Reference

### 3.1 Configuration — `app/config.py`

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `DATABASE_URL` | Yes | `postgresql://agentaudit:agentaudit@localhost:5432/agentaudit` | PostgreSQL connection |
| `REDIS_URL` | No | `redis://localhost:6379/0` | Celery broker/backend |
| `GITHUB_WEBHOOK_SECRET` | Yes | — | Webhook HMAC secret |
| `SECRET_KEY` | Yes | — | Application cryptographic secret |
| `SECURITY_ENVIRONMENT` | No | `development` | `development` enables demo endpoints |

### 3.2 Database layer — `app/database.py` + `app/models.py`

| Model | Purpose |
|---|---|
| `Organization` | Tenant record keyed by `github_installation_id` |
| `ScanAuditLog` | Immutable audit trail with JSONB vulnerability payloads |

Default `author_metadata` on all records: `{"creator": "Naga Sai Mrunal Vuppala"}`.

### 3.3 Security engine — `app/services/security_engine.py`

Combines regex secret scanning with `ASTParser` (tree-sitter + Python `ast` module).

| Category | Examples detected |
|---|---|
| Secrets | AWS `AKIA...`, Stripe `sk_live_...`, GitLab `glpat-...` |
| AST | `eval()`, `exec()`, `os.system()`, `subprocess.run()` |

Memory compliance: diff content cleared in `finally` blocks with `gc.collect()`.

### 3.4 Background workers — `app/tasks.py`

| Item | Value |
|---|---|
| Celery app | `agentaudit` |
| Task | `process_github_webhook_audit(installation_id, payload)` |
| Queue | `agentaudit` (isolated from other local Celery instances) |
| Tenant binding | `SET LOCAL app.current_organization_id = :org_id` before DB writes |

### 3.5 API gateway — `app/main.py`

| Endpoint | Method | Purpose |
|---|---|---|
| `/` | GET | Demo UI dashboard |
| `/health` | GET | Health check (DB + Redis status) |
| `/docs` | GET | Swagger UI |
| `/v1/webhooks/github` | POST | Production webhook ingress |
| `/v1/scan` | POST | Synchronous AST + secret scan |
| `/v1/demo/audit` | POST | Dev-only synchronous audit for UI |
| `/v1/demo/webhook` | POST | Dev-only async pipeline test |

Latency telemetry: every response includes `X-Process-Time-Ms`.

### 3.6 Project structure

```
.
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── README.md
├── LICENSE
├── app/
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── models.py
│   ├── schemas.py
│   ├── tasks.py
│   ├── static/index.html
│   └── services/
│       ├── ast_parser.py
│       └── security_engine.py
├── alembic/env.py
├── agentaudit/client.py
├── docs/PROJECT_DOCUMENTATION.md
└── scripts/
    ├── demo.py
    ├── test_scan_engine.py
    └── generate_word_doc.py
```

---

## 4. Database & Multi-Tenant Isolation

### 4.1 Schema overview

| Table | Column | Type | Purpose |
|---|---|---|---|
| `organizations` | `id` | UUID PK | Canonical tenant identifier |
| `organizations` | `org_name` | VARCHAR(255) | GitHub org / account name |
| `organizations` | `github_installation_id` | VARCHAR(64) UNIQUE | Installation → tenant mapping |
| `organizations` | `author_metadata` | JSONB | Creator attribution |
| `scan_audit_logs` | `organization_id` | UUID FK (indexed) | **RLS isolation key** |
| `scan_audit_logs` | `repository_name` | VARCHAR(512) | `owner/repo` |
| `scan_audit_logs` | `scan_status` | VARCHAR(32) | `passed` or `blocked` |
| `scan_audit_logs` | `vulnerabilities_found` | JSONB | Structured findings |
| `scan_audit_logs` | `metadata_summary` | JSONB | Counts and event metadata |

### 4.2 Row-Level Security policy

```sql
ALTER TABLE scan_audit_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE scan_audit_logs FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_policy ON scan_audit_logs
USING (organization_id = current_setting('app.current_organization_id', true)::uuid);
```

### 4.3 RLS evaluation flow

| Step | Actor | Operation | Outcome |
|---|---|---|---|
| 1 | Celery worker | `SET LOCAL app.current_organization_id` | Binds transaction to tenant |
| 2 | PostgreSQL | Evaluates `USING` on `SELECT` | Returns only matching rows |
| 3 | PostgreSQL | Evaluates policy on `INSERT` | Permits writes for matching tenant only |
| 4 | Cross-tenant query | Any `SELECT` without context | Zero rows returned |

---

## 5. Security & Compliance Design

### 5.1 Regulated organization alignment

| Requirement | How AgentAudit AI addresses it |
|---|---|
| Data minimization | Diff content never stored; only scan metadata persisted |
| Immediate webhook ACK | 202 response prevents GitHub retry storms |
| Secret verification | Rejects unsigned/tampered payloads (403) |
| Memory hygiene | Explicit diff purge + garbage collection |
| Tenant isolation | PostgreSQL RLS + per-installation organization records |
| Audit trail | `scan_audit_logs` with structured JSONB findings |

### 5.2 Production hardening checklist

- [ ] Set `SECURITY_ENVIRONMENT=production`
- [ ] Use managed Redis with TLS
- [ ] Store secrets in Vault (AWS/Azure/HashiCorp)
- [ ] Demo endpoints auto-disable outside development
- [ ] Enable HTTPS termination at load balancer
- [ ] Restrict ingress to GitHub IP ranges
- [ ] Enable centralized logging (Splunk, Datadog, ELK)
- [ ] Rotate `GITHUB_WEBHOOK_SECRET` on schedule

### 5.3 What is NEVER logged

- Raw webhook body
- Diff content
- Matched secret values
- `GITHUB_WEBHOOK_SECRET`

---

## 6. Installation & Operations

### 6.1 Prerequisites

- Docker Desktop (recommended) or Docker Engine + Compose v2
- Python 3.12+ (optional, for local scripts)
- Git

### 6.2 Quick start

```powershell
cd C:\git\github-webhook-audit
copy .env.example .env
docker-compose up --build -d
```

### 6.3 Services

| Service | Port | Role |
|---|---|---|
| `postgres` | 5432 | Multi-tenant metadata store |
| `redis` | 6379 | Celery broker + result backend |
| `web` | 8000 | FastAPI ingress + demo UI |
| `worker` | — | Celery audit processor |

### 6.4 Operational commands

```bash
docker-compose ps
curl http://localhost:8000/health
docker-compose logs web --tail 50
docker-compose logs worker --tail 50
docker-compose logs -f web worker
docker-compose down
```

### 6.5 Manual start (without Docker)

```powershell
# Terminal 1 — PostgreSQL and Redis via Docker
docker run -d -p 5432:5432 -e POSTGRES_USER=agentaudit -e POSTGRES_PASSWORD=agentaudit -e POSTGRES_DB=agentaudit postgres:16-alpine
docker run -d -p 6379:6379 redis:alpine

# Terminal 2 — Worker
python -m celery -A app.tasks.celery_app worker --loglevel=info -Q agentaudit

# Terminal 3 — API
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

> **Windows note:** Celery requires `--pool=solo` when running the worker directly on Windows hosts.

---

## 7. Testing Guide

### 7.1 Test matrix

| Test | Method | Expected |
|---|---|---|
| Health check | `GET /health` | `status: ok`, DB + Redis connected |
| UI dashboard | `GET /` | HTML demo page |
| Clean diff audit | UI → Run audit | `PASS`, 0 violations |
| AWS key leak | UI → AWS example | `FAIL`, high risk |
| Stripe key leak | UI → Stripe example | `FAIL`, high risk |
| AST violation | `POST /v1/scan` with `eval()` | `status: blocked` |
| Invalid signature | Webhook without HMAC | `403 Forbidden` |
| Async pipeline | Queue via webhook flow | `202` + worker logs + DB row |

### 7.2 UI testing (fastest)

1. Open [http://localhost:8000](http://localhost:8000)
2. Click **AWS key leak**
3. Click **Run audit**
4. Expect: **FAIL**, 1 violation, high risk

### 7.3 CLI scripts

```powershell
python scripts\test_scan_engine.py
python scripts\demo.py
python scripts\quick_test.py
```

### 7.4 Validation checklist before go-live

- [ ] All four Docker services healthy
- [ ] `/health` returns `database: connected` and `redis: connected`
- [ ] UI audit PASS/FAIL scenarios work
- [ ] Signed webhook returns 202
- [ ] Unsigned webhook returns 403
- [ ] Worker logs show audit completion without diff content
- [ ] Demo endpoints return 403 when `SECURITY_ENVIRONMENT=production`

---

## 8. Enterprise Integration

### 8.1 GitHub Enterprise Server

1. Deploy AgentAudit AI inside your corporate VPC.
2. Configure webhook URL: `https://audit.internal.company.com/v1/webhooks/github`
3. Match `GITHUB_WEBHOOK_SECRET` with GHES admin settings.
4. Use internal Redis cluster and PostgreSQL with RLS.
5. Forward worker metadata logs to SIEM.

### 8.2 Multi-tenant SaaS deployment

| Concern | Implementation |
|---|---|
| Tenant routing | `github_installation_id` → `organizations.id` |
| Data isolation | PostgreSQL RLS on `scan_audit_logs` |
| Secret isolation | Per-installation webhook secrets (vault-backed) |
| Rate limiting | API gateway / WAF in front of FastAPI |
| Observability | Tag logs with `installation_id` + `repository_name` |

### 8.3 Enterprise security controls

| Control | Recommendation |
|---|---|
| Network | Private subnet behind WAF |
| Secrets | Vault-backed secret injection |
| TLS | Terminate at ALB/NGINX with corporate CA |
| IAM | Service accounts for worker → DB access |
| HA | Multiple Celery workers + Redis Sentinel |

---

## 9. Public Company Integration

### 9.1 Compliance mapping

| Regulation / Framework | Alignment |
|---|---|
| SOX ITGC | Prevent unauthorized credential commits; immutable audit logs |
| SEC Cybersecurity Disclosure | Proactive secret scanning controls |
| GDPR Art. 5 | Data minimization — no diff retention |
| PCI-DSS | Prevent Stripe key leakage in source code |
| NIST CSF | Detect (DE.CM), Respond (RS.AN) |

### 9.2 Board-ready reporting metrics

| Metric | Business value |
|---|---|
| Total audits per quarter | Control operating effectiveness |
| Blocked scan rate | Security posture trend |
| Violations by repository | Targeted developer training |
| Mean time to detect | Incident response KPI |

### 9.3 GitHub.com setup

1. Create GitHub App or Organization Webhook.
2. Payload URL: `https://your-domain.com/v1/webhooks/github`
3. Secret: 32+ char random string → set in `.env`.
4. For local dev, use ngrok: `ngrok http 8000`

---

## 10. API Reference

### `GET /health`

```json
{
  "status": "ok",
  "service": "AgentAuditAI",
  "database": "connected",
  "redis": "connected",
  "environment": "development"
}
```

### `POST /v1/webhooks/github`

**Headers:** `X-Hub-Signature-256`, `Content-Type: application/json`

**Responses:** `202 Accepted` | `403 Forbidden` | `400 Bad Request`

### `POST /v1/demo/audit` (development only)

**Request:**
```json
{"diff": "+def hello():\n+    return 'world'\n"}
```

**Response:**
```json
{
  "status": "PASS",
  "violations": [],
  "high_risk_detected": false
}
```

### `POST /v1/scan`

**Request:**
```json
{
  "files": [
    {"path": "unsafe.py", "content": "result = eval(user_input)\n"}
  ]
}
```

**Response:**
```json
{
  "status": "blocked",
  "reason": "Security Alert: Unauthorized eval() execution detected...",
  "violations": [{"file": "unsafe.py", "line": 1, "category": "ast", "rule": "dangerous_call"}]
}
```

---

## 11. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| UI shows "Not Found" | `/v1/demo/audit` missing or stale container | `docker-compose up --build -d` |
| UI shows 404 | Old process on port 8000 | Run `restart.bat`, use `localhost:8000` |
| `403 Forbidden` | Secret mismatch | Align `.env` with GitHub webhook secret |
| Worker not processing | Redis down or wrong queue | `docker-compose ps`, check `agentaudit` queue |
| Stripe example passes | Demo key too short | Use 24+ chars after `sk_live_` |
| Demo endpoints 403 | `SECURITY_ENVIRONMENT=production` | Expected — use production webhook path |

### Useful commands

```powershell
docker-compose ps
docker-compose logs web --tail 20
docker-compose logs worker --tail 20
docker-compose down && docker-compose up --build -d
```

---

## 12. Roadmap & Extensions

| Version | Feature |
|---|---|
| v2.1 | Admin UI for policy management |
| v2.2 | Custom rule packs per tenant |
| v2.3 | SARIF export for GitHub Advanced Security |
| v2.4 | HashiCorp Vault secret injection |
| v2.5 | Jira / ServiceNow incident automation |

---

## 13. Technology Stack & Rationale

| Organizational need | Technology answer |
|---|---|
| Fast webhook response | FastAPI + async + Celery queue |
| Secret verification | HMAC-SHA256 constant-time compare |
| No diff retention | SecurityEngine memory purge + `gc.collect()` |
| Multi-tenant isolation | PostgreSQL RLS + `SET LOCAL` tenant context |
| AST + secret scanning | tree-sitter + Python `ast` + compiled regex |
| Config safety | Pydantic Settings + `SecretStr` |
| Horizontal scalability | Redis + multiple Celery workers |
| Easy deployment | Docker Compose (4 services) |

### Technologies intentionally NOT used

| Technology | Why not |
|---|---|
| Django | Heavier than needed for a focused webhook API |
| Kafka | Overkill for current volume; Redis is simpler |
| ML / AI scanning | Regex + AST is explainable and auditable |
| Storing diffs in database | Violates data minimization policies |

---

## Appendix A — Environment template

```env
DATABASE_URL=postgresql://agentaudit:agentaudit@postgres:5432/agentaudit
REDIS_URL=redis://redis:6379/0
GITHUB_WEBHOOK_SECRET=your-32-char-minimum-secret
SECRET_KEY=your-long-random-secret-key
SECURITY_ENVIRONMENT=development
```

## Appendix B — Contact & support

- **Repository:** [github.com/mrunalvuppala/github-webhook-audit](https://github.com/mrunalvuppala/github-webhook-audit)
- **Issues:** GitHub Issues tab on the repository
- **Word documentation:** Run `python scripts/generate_word_doc.py` or double-click `download-word-doc.bat`

---

*This document is intended for technical teams, security engineers, compliance officers, and platform architects evaluating or operating AgentAudit AI in enterprise and public company environments.*
