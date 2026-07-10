# AgentAuditAI — Complete Project & Technical Documentation

**Version:** 1.0.0  
**Author:** Naga Sai Mrunal Vuppala ([@mrunalvuppala](https://github.com/mrunalvuppala))  
**Repository:** [github.com/mrunalvuppala/github-webhook-audit](https://github.com/mrunalvuppala/github-webhook-audit)  
**Last Updated:** July 2026

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [System Architecture](#2-system-architecture)
3. [Component Reference](#3-component-reference)
4. [Security & Compliance Design](#4-security--compliance-design)
5. [Installation & Operations](#5-installation--operations)
6. [Testing Guide](#6-testing-guide)
7. [Enterprise Integration](#7-enterprise-integration)
8. [Public Company Integration](#8-public-company-integration)
9. [API Reference](#9-api-reference)
10. [Troubleshooting](#10-troubleshooting)
11. [Roadmap & Extensions](#11-roadmap--extensions)
12. [Technology Stack & Rationale](#12-technology-stack--rationale)

---

## 1. Executive Summary

**AgentAuditAI** is a compliance-oriented GitHub webhook gateway that verifies incoming events, queues asynchronous credential audits, and returns immediate acknowledgment to GitHub. It is designed for organizations that must prevent secret leakage in code while meeting strict data retention and privacy requirements.

### Key capabilities

| Capability | Description |
|---|---|
| Webhook verification | HMAC-SHA256 signature validation via `X-Hub-Signature-256` |
| Asynchronous auditing | Celery workers process diffs in the background |
| Credential detection | AWS, Stripe, and GitLab token patterns |
| Memory safety | Diff content is never logged, stored, or retained beyond local scope |
| Multi-tenant ready | Supports `tenant_id` and GitHub `installation` metadata |
| Demo UI | Browser dashboard for live presentations and QA |

### Technology stack

| Layer | Technology |
|---|---|
| API Gateway | FastAPI + Uvicorn |
| Configuration | Pydantic Settings v2 |
| Task Queue | Celery + Redis |
| Audit Engine | Stateless regex scanner (Python) |
| Deployment | Docker Compose |

---

## 2. System Architecture

### High-level data flow

```mermaid
flowchart TB
    subgraph External
        GH[GitHub / GitHub Enterprise]
    end

    subgraph Gateway["API Gateway (FastAPI)"]
        WH["POST /v1/webhooks/github"]
        HMAC[HMAC-SHA256 Verify]
        PARSE[Parse tenant + installation]
    end

    subgraph Queue["Message Broker"]
        REDIS[(Redis)]
    end

    subgraph Workers["Background Processing"]
        CELERY[Celery Worker]
        ENGINE[StatelessAuditEngine]
    end

    subgraph Storage["Metadata Only"]
        DB[(Tenant Config DB)]
        LOGS[Structured Logs]
    end

    subgraph Demo["Development UI"]
        UI["GET /"]
        DEMO["POST /v1/demo/audit"]
    end

    GH -->|Signed webhook| WH
    WH --> HMAC
    HMAC -->|403 if invalid| GH
    HMAC -->|202 Accepted| GH
    HMAC --> PARSE
    PARSE -->|delay()| REDIS
    REDIS --> CELERY
    CELERY --> ENGINE
    ENGINE -->|metadata only| DB
    ENGINE -->|metadata only| LOGS
    UI --> DEMO
    DEMO --> ENGINE
```

### Request lifecycle (production webhook)

1. GitHub delivers `POST /v1/webhooks/github` with raw JSON body.
2. Gateway reads **raw bytes** (`await request.body()`) to preserve signature integrity.
3. `GITHUB_WEBHOOK_SECRET` is used to compute expected `sha256=` digest.
4. `hmac.compare_digest` performs constant-time comparison.
5. On success, JSON is parsed for `tenant_id`, `installation.id`, and `diff`.
6. `execute_asynchronous_audit.delay()` enqueues the job.
7. Gateway returns **HTTP 202 Accepted** immediately.
8. Worker runs `StatelessAuditEngine.inspect_diff()`.
9. Only audit **metadata** is logged and persisted.

---

## 3. Component Reference

### 3.1 Configuration layer — `app/core/config.py`

Loads environment variables via `pydantic-settings`.

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `REDIS_URL` | No | `redis://localhost:6379/0` | Celery broker/backend |
| `GITHUB_WEBHOOK_SECRET` | **Yes** | — | Webhook HMAC secret |
| `DATABASE_URL` | **Yes** | — | Tenant configuration cache |
| `MEMORY_RETENTION_LIMIT_MB` | No | `50` | Parsing memory ceiling |
| `ENVIRONMENT` | No | `development` | `development` / `staging` / `production` |

Development safety: prints a warning when running in development with a non-production database URL (no credentials exposed).

### 3.2 Audit engine — `app/services/audit_engine.py`

**Class:** `StatelessAuditEngine`  
**Output schema:** `AuditResult`

```python
class AuditResult:
    status: str              # "PASS" or "FAIL"
    violations: list[dict] # line, rule, risk_level
    high_risk_detected: bool
```

#### Detection rules

| Rule ID | Pattern | Risk |
|---|---|---|
| `aws_access_key_id` | `AKIA[0-9A-Z]{16}` | High |
| `aws_secret_access_key` | AWS secret key assignment | High |
| `stripe_live_secret_key` | `sk_live_*` | High |
| `stripe_live_restricted_key` | `rk_live_*` | High |
| `stripe_test_secret_key` | `sk_test_*` | Medium |
| `gitlab_access_token` | `glpat-*` | High |

#### Memory compliance (critical)

- `diff_content` never assigned to instance/module scope
- Never printed or logged
- Line buffers cleared in `finally` block
- `gc.collect()` invoked after purge

### 3.3 Background workers — `app/workers/tasks.py`

**Celery app:** `celery_app`  
**Task:** `execute_asynchronous_audit(tenant_id, installation_id, diff_payload)`

Logs only: `status`, `violation_count`, `high_risk_detected`, `tenant_id`, `installation_id`.

### 3.4 API gateway — `app/main.py`

| Endpoint | Method | Purpose |
|---|---|---|
| `/` | GET | Demo UI dashboard |
| `/health` | GET | Health check |
| `/docs` | GET | Swagger UI |
| `/v1/webhooks/github` | POST | Production webhook ingress |
| `/v1/demo/audit` | POST | Dev-only synchronous audit |
| `/v1/demo/webhook` | POST | Dev-only Celery queue test |

---

## 4. Security & Compliance Design

### 4.1 Why this matters for regulated organizations

| Requirement | How AgentAuditAI addresses it |
|---|---|
| **Data minimization** | Only audit metadata stored; never raw diffs |
| **Immediate webhook ACK** | 202 response prevents GitHub retry storms |
| **Secret verification** | Rejects unsigned/tampered payloads (403) |
| **Memory hygiene** | Explicit diff purge + garbage collection |
| **Audit trail** | Structured logs with tenant/installation IDs |
| **Tenant isolation** | `tenant_id` propagated through task pipeline |

### 4.2 Production hardening checklist

- [ ] Set `ENVIRONMENT=production`
- [ ] Use managed Redis (TLS-enabled)
- [ ] Store secrets in vault (AWS Secrets Manager, Azure Key Vault, HashiCorp Vault)
- [ ] Disable demo endpoints (automatic when `ENVIRONMENT != development`)
- [ ] Enable HTTPS termination at load balancer / API gateway
- [ ] Restrict ingress to GitHub IP ranges
- [ ] Connect `DATABASE_URL` to production tenant cache
- [ ] Enable centralized logging (Splunk, Datadog, ELK)
- [ ] Rotate `GITHUB_WEBHOOK_SECRET` on schedule

### 4.3 What is NEVER logged

- Raw webhook body
- Diff content
- Matched secret values
- `GITHUB_WEBHOOK_SECRET`

---

## 5. Installation & Operations

### 5.1 Prerequisites

- Docker Desktop (recommended) **or** Python 3.12+
- Redis 6+
- PostgreSQL (or compatible DB for tenant cache)

### 5.2 Quick start (Docker — recommended)

```powershell
cd C:\git\github-webhook-audit
copy .env.example .env
start.bat
```

Services started:

| Service | Port | Role |
|---|---|---|
| `api` | 8000 | FastAPI gateway + UI |
| `redis` | 6379 | Celery broker |
| `worker` | — | Background audits |

### 5.3 Restart

```powershell
restart.bat
```

### 5.4 Manual start (no Docker)

```powershell
# Terminal 1
docker run -d -p 6379:6379 redis:alpine

# Terminal 2
python -m celery -A app.workers.tasks.celery_app worker --loglevel=info --pool=solo

# Terminal 3
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

> **Windows note:** Celery requires `--pool=solo` on Windows hosts.

### 5.5 Project structure

```
github-webhook-audit/
├── app/
│   ├── core/
│   │   └── config.py           # Pydantic settings
│   ├── services/
│   │   └── audit_engine.py     # Credential scanner
│   ├── workers/
│   │   └── tasks.py            # Celery tasks
│   ├── static/
│   │   └── index.html          # Demo UI
│   └── main.py                 # FastAPI gateway
├── docs/
│   └── PROJECT_DOCUMENTATION.md
├── scripts/
│   └── demo.py                 # CLI demo script
├── docker-compose.yml
├── Dockerfile
├── start.bat
├── restart.bat
├── demo.bat
├── requirements.txt
└── .env.example
```

---

## 6. Testing Guide

### 6.1 Test matrix

| Test | Method | Expected |
|---|---|---|
| Health check | `GET /health` | `200 {"status":"ok"}` |
| UI dashboard | `GET /` | `200` HTML page |
| Clean diff audit | UI → Run audit | `PASS`, 0 violations |
| AWS key leak | UI → AWS example | `FAIL`, high risk |
| Stripe key leak | UI → Stripe example | `FAIL`, high risk |
| Invalid signature | Webhook without HMAC | `403 Forbidden` |
| Async pipeline | Queue via webhook flow | `202` + worker logs |

### 6.2 UI testing (fastest)

1. Open [http://localhost:8000](http://localhost:8000)
2. Click **AWS key leak**
3. Click **Run audit**
4. Expect: **FAIL**, 1 violation, high risk

### 6.3 CLI demo script

```powershell
cd C:\git\github-webhook-audit
python scripts\demo.py
```

### 6.4 Signed webhook test (PowerShell)

```powershell
python -c @"
import hmac, hashlib, json, urllib.request

secret = 'replace-with-your-webhook-secret'
payload = {
    'tenant_id': 'acme-corp',
    'installation': {'id': 99001, 'account': {'login': 'acme-enterprise'}},
    'diff': \"+API_KEY = 'AKIAIOSFODNN7EXAMPLE'\n\"
}
body = json.dumps(payload).encode()
sig = 'sha256=' + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

req = urllib.request.Request(
    'http://localhost:8000/v1/webhooks/github',
    data=body,
    headers={'Content-Type': 'application/json', 'X-Hub-Signature-256': sig},
    method='POST'
)
resp = urllib.request.urlopen(req)
print('Status:', resp.status)
"@
```

**Expected:** `Status: 202`

Check worker logs:

```powershell
docker compose logs worker --tail 10
```

### 6.5 Validation checklist before go-live

- [ ] All Docker services healthy
- [ ] `/health` returns 200
- [ ] UI audit PASS/FAIL scenarios work
- [ ] Signed webhook returns 202
- [ ] Unsigned webhook returns 403
- [ ] Worker logs show metadata only (no diff content)
- [ ] Demo endpoints return 403 when `ENVIRONMENT=production`

---

## 7. Enterprise Integration

### 7.1 GitHub Enterprise Server (GHES)

For on-premises GitHub Enterprise:

1. Deploy AgentAuditAI inside your corporate VPC.
2. Configure GHES webhook URL:
   ```
   https://audit.internal.company.com/v1/webhooks/github
   ```
3. Set webhook secret in GHES admin → match `GITHUB_WEBHOOK_SECRET`.
4. Select events: `push`, `pull_request`, `installation`.
5. Use internal Redis cluster and PostgreSQL for tenant cache.

```mermaid
flowchart LR
    GHES[GitHub Enterprise Server] --> LB[Internal Load Balancer]
    LB --> API[AgentAuditAI API]
    API --> Redis[Enterprise Redis]
    API --> PG[PostgreSQL Tenant DB]
    API --> SIEM[SIEM / Splunk]
```

### 7.2 Multi-tenant SaaS deployment

For MSPs or platform vendors serving multiple enterprise clients:

| Concern | Implementation |
|---|---|
| Tenant routing | Map `installation.account.login` → `tenant_id` |
| Config cache | `DATABASE_URL` stores per-tenant policy rules |
| Secret isolation | Per-tenant webhook secrets (future: secret rotation table) |
| Rate limiting | API gateway / WAF in front of FastAPI |
| Observability | Tag logs with `tenant_id` + `installation_id` |

### 7.3 Enterprise security controls

| Control | Recommendation |
|---|---|
| Network | Private subnet, no public ingress except through WAF |
| Secrets | Vault-backed `GITHUB_WEBHOOK_SECRET` injection |
| TLS | Terminate at ALB/NGINX with corporate CA |
| IAM | Service accounts for worker → DB access |
| Audit | Forward worker metadata logs to SIEM |
| HA | Horizontal scale: multiple Celery workers + Redis Sentinel |

### 7.4 CI/CD pipeline integration

```yaml
# Example: Azure DevOps / GitHub Actions smoke test
- name: Health check
  run: curl -f http://audit-api:8000/health

- name: Audit smoke test
  run: python scripts/demo.py
```

### 7.5 Policy engine extension (recommended)

Replace mock `_record_audit_result` with:

- **Jira** ticket creation on `high_risk_detected`
- **ServiceNow** incident for public company SOX controls
- **Slack/Teams** alert to security channel
- **AWS Security Hub** finding export

---

## 8. Public Company Integration

Public companies face additional scrutiny (SOX, SEC cybersecurity rules, GDPR for EU subsidiaries).

### 8.1 Compliance mapping

| Regulation / Framework | AgentAuditAI alignment |
|---|---|
| **SOX ITGC** | Prevent unauthorized credential commits; audit trail of violations |
| **SEC Cybersecurity Disclosure** | Demonstrate proactive secret scanning controls |
| **GDPR Art. 5** | Data minimization — no diff retention |
| **PCI-DSS** | Prevent Stripe key leakage in source code |
| **NIST CSF** | Detect (DE.CM), Respond (RS.AN) |

### 8.2 Public company deployment pattern

```mermaid
flowchart TB
    subgraph Internet
        GHC[GitHub Cloud]
    end

    subgraph DMZ
        WAF[Cloud WAF]
    end

    subgraph PrivateCloud
        API[AgentAuditAI]
        REDIS[Redis]
        WORKER[Celery Workers]
        DB[(Audit Metadata DB)]
    end

    subgraph GRC
        SIEM[SIEM]
        GRC2[GRC Platform]
        LEGAL[Legal Hold Archive]
    end

    GHC --> WAF --> API
    API --> REDIS --> WORKER
    WORKER --> DB
    WORKER --> SIEM
    DB --> GRC2
    SIEM --> LEGAL
```

### 8.3 Board-ready reporting metrics

Export from audit metadata store:

| Metric | Business value |
|---|---|
| Total audits per quarter | Control operating effectiveness |
| High-risk detection rate | Security posture trend |
| Mean time to detect | Incident response KPI |
| Violations by tenant/repo | Targeted developer training |
| False positive rate | Rule tuning effectiveness |

### 8.4 GitHub.com (public cloud) setup

1. Create GitHub App or Organization Webhook.
2. Payload URL: `https://your-domain.com/v1/webhooks/github`
3. Content type: `application/json`
4. Secret: generate 32+ char random string → set in `.env`.
5. For local dev, use ngrok:
   ```powershell
   ngrok http 8000
   ```
6. Enable SSL — GitHub requires HTTPS for production webhooks.

### 8.5 Data residency

For EU public companies:

- Deploy API + workers in EU region (e.g., `eu-west-1`)
- Use EU-hosted Redis and PostgreSQL
- Ensure metadata DB does not replicate to non-EU regions
- Document diff non-retention in privacy impact assessment (PIA)

---

## 9. API Reference

### `GET /health`

```json
{"status": "ok", "service": "AgentAuditAI"}
```

### `POST /v1/webhooks/github`

**Headers:**
- `X-Hub-Signature-256: sha256=<hmac_hex>`
- `Content-Type: application/json`

**Body (example):**
```json
{
  "tenant_id": "acme-corp",
  "installation": {
    "id": 12345,
    "account": {"login": "acme-enterprise"}
  },
  "diff": "+AWS_KEY = 'AKIAIOSFODNN7EXAMPLE'\n"
}
```

**Responses:**
| Code | Meaning |
|---|---|
| 202 | Accepted and queued |
| 403 | Invalid/missing signature |
| 400 | Malformed JSON |

### `POST /v1/demo/audit` (development only)

**Body:**
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

---

## 10. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| UI shows 404 | Old process on port 8000 | Run `restart.bat`, use `localhost:8000` |
| `403 Forbidden` | Secret mismatch | Align `.env` with GitHub webhook secret |
| Worker not processing | Redis down | `docker compose ps`, restart Redis |
| Docker won't start | Docker Desktop off | Start Docker Desktop first |
| Celery fails on Windows | Prefork pool | Use `--pool=solo` |
| Demo endpoints 403 | `ENVIRONMENT=production` | Expected — use production webhook path |

### Useful commands

```powershell
docker compose ps
docker compose logs api --tail 20
docker compose logs worker --tail 20
docker compose down && docker compose up --build
```

---

## 11. Roadmap & Extensions

| Phase | Feature |
|---|---|
| v1.1 | GitHub App auto-registration |
| v1.2 | Custom rule packs per tenant |
| v1.3 | SARIF export for GitHub Advanced Security |
| v1.4 | HashiCorp Vault secret injection |
| v2.0 | Real database persistence (replace mock callback) |
| v2.1 | Admin UI for policy management |

---

## 12. Technology Stack & Rationale

This section explains every major technology used in AgentAuditAI and the engineering reasons behind each choice.

### 12.1 Core language

#### Python 3.12

| Aspect | Detail |
|---|---|
| **Used for** | API gateway, audit engine, background workers, configuration, documentation tooling |
| **Why chosen** | Mature ecosystem for security tooling, fast to develop, excellent regex/HMAC support, widely adopted in enterprise DevSecOps teams |
| **Enterprise fit** | Easy to hire for, integrates with SIEM/vault/CI pipelines, runs consistently in Docker |

---

### 12.2 API layer

#### FastAPI

| Aspect | Detail |
|---|---|
| **Used for** | Webhook gateway, demo UI routes, health checks, OpenAPI docs |
| **Why chosen** | High-performance async HTTP, automatic request validation, built-in Swagger UI at `/docs` |
| **Project need** | GitHub webhooks require sub-second HMAC verification and immediate `202 Accepted` responses |

#### Uvicorn

| Aspect | Detail |
|---|---|
| **Used for** | ASGI server hosting the FastAPI application |
| **Why chosen** | Lightweight, production-ready, standard pairing with FastAPI |
| **Project need** | Reliable local and containerized API serving on port 8000 |

---

### 12.3 Configuration management

#### Pydantic v2 + pydantic-settings

| Aspect | Detail |
|---|---|
| **Used for** | Loading `REDIS_URL`, `GITHUB_WEBHOOK_SECRET`, `DATABASE_URL`, and other env vars |
| **Why chosen** | Type-safe validation at startup, `SecretStr` prevents accidental secret exposure |
| **Project need** | Fail fast on misconfiguration; enforce required secrets before processing webhooks |

#### python-dotenv

| Aspect | Detail |
|---|---|
| **Used for** | Loading `.env` files in local development |
| **Why chosen** | Standard developer workflow; keeps secrets out of source code |
| **Project need** | Simple onboarding for demos and local testing |

---

### 12.4 Security & audit engine

#### HMAC + hashlib (Python standard library)

| Aspect | Detail |
|---|---|
| **Used for** | Verifying `X-Hub-Signature-256` on incoming GitHub webhooks |
| **Why chosen** | Native, auditable, no extra dependencies; `hmac.compare_digest` prevents timing attacks |
| **Project need** | Reject tampered payloads before any diff content is processed |

#### Compiled regex (`re` module)

| Aspect | Detail |
|---|---|
| **Used for** | Detecting AWS, Stripe, and GitLab credential patterns in diffs |
| **Why chosen** | Fast, stateless, explainable rules — no ML black box |
| **Project need** | Compliance teams need auditable, predictable detection logic |

#### `gc` (garbage collector)

| Aspect | Detail |
|---|---|
| **Used for** | Purging diff content from memory after each audit |
| **Why chosen** | Reinforces the no-retention policy beyond simple variable deletion |
| **Project need** | Public company data minimization (GDPR Art. 5) and internal security policy |

---

### 12.5 Background processing

#### Celery

| Aspect | Detail |
|---|---|
| **Used for** | `execute_asynchronous_audit` background task |
| **Why chosen** | Industry-standard distributed task queue for Python |
| **Project need** | Decouple webhook ACK from diff scanning; GitHub expects fast responses |

#### Redis

| Aspect | Detail |
|---|---|
| **Used for** | Celery message broker and result backend |
| **Why chosen** | Fast, reliable, horizontally scalable, widely deployed in enterprises |
| **Project need** | Queue audit jobs between API and worker with minimal latency |

---

### 12.6 Data & storage

#### PostgreSQL (via `DATABASE_URL`)

| Aspect | Detail |
|---|---|
| **Used for** | Tenant configuration caching and audit metadata (production target) |
| **Why chosen** | Enterprise-standard RDBMS with strong audit and compliance track record |
| **Project need** | Multi-tenant policy storage with structured query and reporting |

#### Mock metadata callback (current implementation)

| Aspect | Detail |
|---|---|
| **Used for** | Simulating persistence of audit outcomes during development |
| **Why chosen** | Keeps the demo self-contained; easy to replace with Jira, ServiceNow, or SIEM |
| **Project need** | Show end-to-end pipeline without locking into one enterprise system |

---

### 12.7 Frontend & demo tooling

#### HTML + JavaScript (static dashboard)

| Aspect | Detail |
|---|---|
| **Used for** | Browser UI at `/` for live demos and QA |
| **Why chosen** | Zero build step, instant load, calls `/v1/demo/audit` for real-time results |
| **Project need** | Presentation-ready interface for stakeholders and security reviewers |

#### Batch scripts (`start.bat`, `restart.bat`, `demo.bat`)

| Aspect | Detail |
|---|---|
| **Used for** | One-click startup, restart, and CLI demo on Windows |
| **Why chosen** | Reduces friction for non-CLI users during demos |
| **Project need** | Fast, repeatable demonstrations in enterprise meetings |

---

### 12.8 Deployment & operations

#### Docker + Docker Compose

| Aspect | Detail |
|---|---|
| **Used for** | Running API, Redis, and Worker as a unified stack |
| **Why chosen** | Reproducible environments, matches enterprise microservice deployment patterns |
| **Project need** | One-command startup; eliminates local dependency conflicts |

#### Dockerfile (Python 3.12-slim)

| Aspect | Detail |
|---|---|
| **Used for** | Container image for API and worker services |
| **Why chosen** | Small image size, consistent Python runtime across environments |
| **Project need** | Portable builds for cloud and on-premises enterprise deployment |

---

### 12.9 Documentation tooling

#### python-docx + matplotlib

| Aspect | Detail |
|---|---|
| **Used for** | Generating Word documentation with embedded architecture diagrams |
| **Why chosen** | Produces stakeholder-ready `.docx` deliverables with visual pages |
| **Project need** | Compliance officers and executives need formatted documents, not just README files |

---

### 12.10 Architecture technology map

```mermaid
flowchart LR
    GH[GitHub] --> FastAPI[FastAPI + Uvicorn]
    FastAPI --> Redis[Redis]
    Redis --> Celery[Celery Worker]
    Celery --> Engine[Regex Audit Engine]
    Engine --> Meta[Metadata / Logs]
    Config[Pydantic Settings] --> FastAPI
    Config --> Celery
```

---

### 12.11 Why this stack fits enterprise & public companies

| Organizational need | Technology answer |
|---|---|
| Fast webhook response | FastAPI + async + Celery queue |
| Secret verification | HMAC-SHA256 with constant-time compare |
| No diff retention | Stateless engine + `gc.collect()` |
| Config safety | Pydantic Settings + `SecretStr` |
| Horizontal scalability | Redis + multiple Celery workers |
| Compliance audit trail | Metadata-only structured logging |
| Easy deployment | Docker Compose |
| SIEM / vault / GHES integration | Modular Python services |

---

### 12.12 Technologies intentionally NOT used

| Technology | Why not used |
|---|---|
| **Django** | Heavier than needed for a focused webhook API |
| **Kafka** | Overkill for current queue volume; Redis is simpler to operate |
| **ML / AI scanning** | Regex is faster, explainable, and auditable for known credential formats |
| **Storing diffs in a database** | Violates data minimization and compliance retention policies |
| **React / Vue SPA** | Unnecessary build complexity for a demo dashboard |

---

### 12.13 Summary

AgentAuditAI uses a **Python + FastAPI + Celery + Redis** architecture to deliver a **fast, compliant, asynchronously audited GitHub webhook gateway**. Every technology choice prioritizes **speed, explainability, data minimization, and enterprise deployability** over unnecessary complexity.

---

## Appendix A — Environment file template

```env
GITHUB_WEBHOOK_SECRET=your-32-char-minimum-secret
DATABASE_URL=postgresql://user:pass@db-host:5432/tenant_cache
REDIS_URL=redis://redis-host:6379/0
MEMORY_RETENTION_LIMIT_MB=50
ENVIRONMENT=production
```

## Appendix B — Contact & support

- **Repository:** [github.com/mrunalvuppala/github-webhook-audit](https://github.com/mrunalvuppala/github-webhook-audit)
- **Issues:** GitHub Issues tab on the repository

---

*This document is intended for technical teams, security engineers, compliance officers, and platform architects evaluating or operating AgentAuditAI in enterprise and public company environments.*
