"""FastAPI ingress gateway for AgentAudit AI multi-tenant infrastructure.

Architecture designed, engineered, and maintained by Naga Sai Mrunal Vuppala.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import redis
from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from app.config import Settings, get_settings
from app.database import check_database_connection, initialize_database
from app.schemas import (
    DemoAuditRequest,
    DemoAuditResponse,
    HealthResponse,
    ScanRequest,
    ScanResponse,
    WebhookAcceptedResponse,
)
from app.services.security_engine import SecurityEngine
from app.tasks import process_github_webhook_audit

logger = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).resolve().parent / "static"
_security_engine = SecurityEngine()


class DemoWebhookRequest(BaseModel):
    tenant_id: str = "demo-tenant"
    installation_id: str = "4242"
    diff: str = Field(description="Unified diff content to queue for audit.")
    repository_name: str = "demo-org/demo-repo"
    pull_request_number: int | None = None
    commit_sha: str | None = None


def _to_demo_audit_result(scan: ScanResponse) -> DemoAuditResponse:
    violations: list[dict[str, Any]] = []
    for item in scan.violations:
        risk_level = "high" if item.get("category") == "secret" else "medium"
        violations.append(
            {
                "line": item.get("line"),
                "rule": item.get("rule"),
                "risk_level": risk_level,
                "detail": item.get("detail"),
            }
        )

    high_risk_detected = any(v["risk_level"] == "high" for v in violations)
    return DemoAuditResponse(
        status="FAIL" if scan.status == "blocked" else "PASS",
        violations=violations,
        high_risk_detected=high_risk_detected,
    )


def _verify_github_signature(
    body: bytes,
    signature_header: str | None,
    secret: str,
) -> bool:
    if not signature_header:
        return False

    expected_signature = (
        "sha256="
        + hmac.new(
            secret.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()
    )
    return hmac.compare_digest(expected_signature, signature_header)


def _extract_installation_id(payload: dict[str, Any]) -> str:
    installation = payload.get("installation") or {}
    if installation_id := installation.get("id"):
        return str(installation_id)
    return "unknown"


def _check_redis_connection(redis_url: str) -> bool:
    try:
        client = redis.Redis.from_url(redis_url, socket_connect_timeout=2)
        return bool(client.ping())
    except Exception as exc:
        logger.error("Redis connectivity check failed: %s", exc)
        return False


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    initialize_database()
    logger.info(
        "AgentAudit AI started environment=%s database_url_configured=%s",
        settings.security_environment,
        bool(settings.database_url),
    )
    yield


app = FastAPI(
    title="AgentAudit AI",
    description="Production-grade multi-tenant GitHub webhook security auditing platform.",
    version="2.0.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def latency_telemetry_middleware(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - start) * 1000
    response.headers["X-Process-Time-Ms"] = f"{elapsed_ms:.2f}"
    response.headers["X-AgentAudit-Service"] = "AgentAuditAI"
    return response


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    settings = get_settings()
    database_ok = check_database_connection()
    redis_ok = _check_redis_connection(settings.redis_url)

    return HealthResponse(
        status="ok" if database_ok and redis_ok else "degraded",
        service="AgentAuditAI",
        database="connected" if database_ok else "unavailable",
        redis="connected" if redis_ok else "unavailable",
        environment=settings.security_environment,
    )


@app.get("/", response_model=None)
async def dashboard():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return JSONResponse(
        {
            "service": "AgentAuditAI",
            "version": "2.0.0",
            "docs": "/docs",
            "health": "/health",
        }
    )


@app.post("/v1/scan", response_model=ScanResponse)
async def scan_files(request: ScanRequest) -> ScanResponse:
    return _security_engine.scan_files(request.files)


@app.post("/v1/demo/audit", response_model=DemoAuditResponse)
async def demo_audit(request: DemoAuditRequest) -> DemoAuditResponse:
    """Run a synchronous audit for the browser demo UI."""
    settings = get_settings()
    if not settings.is_development:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Demo endpoints are only available in development mode",
        )

    scan_result = _security_engine.scan_diff(request.diff)
    return _to_demo_audit_result(scan_result)


@app.post("/v1/demo/webhook", response_model=WebhookAcceptedResponse)
async def demo_webhook(request: DemoWebhookRequest) -> WebhookAcceptedResponse:
    settings = get_settings()
    if not settings.is_development:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Demo endpoints are only available in development mode",
        )

    payload = {
        "installation": {"id": request.installation_id},
        "repository": {"full_name": request.repository_name},
        "pull_request": {"number": request.pull_request_number},
        "after": request.commit_sha,
        "diff": request.diff,
        "action": "demo",
    }

    process_github_webhook_audit.delay(request.installation_id, payload)
    return WebhookAcceptedResponse(
        installation_id=request.installation_id,
        tenant_id=request.tenant_id,
    )


@app.post(
    "/v1/webhooks/github",
    status_code=status.HTTP_202_ACCEPTED,
    response_class=Response,
)
async def github_webhook(request: Request) -> Response:
    settings: Settings = get_settings()
    body = await request.body()
    signature_header = request.headers.get("X-Hub-Signature-256")

    webhook_secret = settings.github_webhook_secret.get_secret_value()
    if not _verify_github_signature(body, signature_header, webhook_secret):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden",
        )

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload",
        ) from exc

    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Webhook payload must be a JSON object",
        )

    installation_id = _extract_installation_id(payload)
    process_github_webhook_audit.delay(installation_id, payload)

    logger.info("GitHub webhook accepted installation_id=%s", installation_id)
    return Response(status_code=status.HTTP_202_ACCEPTED)


def bootstrap() -> Settings:
    return get_settings()


if __name__ == "__main__":
    import uvicorn

    bootstrap()
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)
