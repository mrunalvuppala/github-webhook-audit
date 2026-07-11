"""FastAPI gateway for GitHub webhook ingestion and asynchronous audit dispatch."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from contextlib import asynccontextmanager
from typing import Any

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.core.config import Settings, get_settings
from app.schemas.scan import ScanRequest, ScanResponse
from app.services.audit_engine import AuditResult, StatelessAuditEngine
from app.services.scan_engine import ASTScanEngine
from app.workers.tasks import execute_asynchronous_audit

logger = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).resolve().parent / "static"


class DemoAuditRequest(BaseModel):
    diff: str = Field(description="Unified diff content to inspect.")


class DemoWebhookRequest(BaseModel):
    tenant_id: str = "demo-tenant"
    installation_id: str = "4242"
    diff: str = Field(description="Unified diff content to queue for audit.")


_scan_engine = ASTScanEngine()


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


def _extract_tenant_id(payload: dict[str, Any]) -> str:
    if tenant_id := payload.get("tenant_id"):
        return str(tenant_id)

    installation = payload.get("installation") or {}
    account = installation.get("account") or {}
    if account_id := account.get("login") or account.get("id"):
        return str(account_id)

    organization = payload.get("organization") or {}
    if org_id := organization.get("login") or organization.get("id"):
        return str(org_id)

    repository = payload.get("repository") or {}
    owner = repository.get("owner") or {}
    if owner_id := owner.get("login") or owner.get("id"):
        return str(owner_id)

    return "unknown"


def _extract_installation_id(payload: dict[str, Any]) -> str:
    installation = payload.get("installation") or {}
    if installation_id := installation.get("id"):
        return str(installation_id)
    return "unknown"


def _extract_diff_payload(payload: dict[str, Any]) -> str:
    if isinstance(payload.get("diff"), str):
        return payload["diff"]
    if isinstance(payload.get("diff_payload"), str):
        return payload["diff_payload"]
    return ""


@asynccontextmanager
async def lifespan(_: FastAPI):
    get_settings()
    yield


app = FastAPI(
    title="AgentAuditAI",
    description="High-performance AST and secret scanning engine with GitHub webhook gateway.",
    version="2.0.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Simple health endpoint for demos and load balancers."""
    return {"status": "ok", "service": "AgentAuditAI"}


@app.get("/")
async def dashboard() -> FileResponse:
    """Presentation dashboard for live credential audit demos."""
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/v1/demo/audit", response_model=AuditResult)
async def demo_audit(request: DemoAuditRequest) -> AuditResult:
    """Run a synchronous audit for the browser demo UI."""
    settings = get_settings()
    if not settings.is_development:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Demo endpoints are only available in development mode",
        )

    engine = StatelessAuditEngine()
    return engine.inspect_diff(request.diff)


@app.post("/v1/demo/webhook")
async def demo_webhook(request: DemoWebhookRequest) -> dict[str, str]:
    """Queue a demo payload through the real webhook + Celery path."""
    settings = get_settings()
    if not settings.is_development:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Demo endpoints are only available in development mode",
        )

    execute_asynchronous_audit.delay(
        request.tenant_id,
        request.installation_id,
        request.diff,
    )

    return {
        "status": "accepted",
        "tenant_id": request.tenant_id,
        "installation_id": request.installation_id,
    }


@app.post("/v1/scan", response_model=ScanResponse)
async def scan_files(request: ScanRequest) -> ScanResponse:
    """High-throughput AST and secret scan endpoint for pre-commit and CI clients."""
    return _scan_engine.scan_files(request.files)


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

    tenant_id = _extract_tenant_id(payload)
    installation_id = _extract_installation_id(payload)
    diff_payload = _extract_diff_payload(payload)

    execute_asynchronous_audit.delay(tenant_id, installation_id, diff_payload)

    logger.info(
        "GitHub webhook accepted tenant_id=%s installation_id=%s",
        tenant_id,
        installation_id,
    )

    return Response(status_code=status.HTTP_202_ACCEPTED)


def bootstrap() -> Settings:
    """Load configuration and run startup safety checks."""
    return get_settings()


if __name__ == "__main__":
    import uvicorn

    bootstrap()
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)
