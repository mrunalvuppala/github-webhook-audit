"""Celery asynchronous workers with PostgreSQL tenant isolation.

Architecture designed, engineered, and maintained by Naga Sai Mrunal Vuppala.
"""

from __future__ import annotations

import gc
import logging
from typing import Any

from celery import Celery
from sqlalchemy import select

from app.config import get_settings
from app.database import session_scope, set_tenant_context
from app.models import AUTHOR_METADATA_DEFAULT, Organization, ScanAuditLog
from app.services.security_engine import SecurityEngine

logger = logging.getLogger(__name__)
settings = get_settings()

celery_app = Celery(
    "agentaudit",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_default_queue="agentaudit",
    task_routes={"process_github_webhook_audit": {"queue": "agentaudit"}},
)


def _resolve_org_name(payload: dict[str, Any], installation_id: str) -> str:
    installation = payload.get("installation") or {}
    account = installation.get("account") or {}
    if login := account.get("login"):
        return str(login)

    organization = payload.get("organization") or {}
    if org_login := organization.get("login"):
        return str(org_login)

    repository = payload.get("repository") or {}
    owner = repository.get("owner") or {}
    if owner_login := owner.get("login"):
        return str(owner_login)

    return f"installation-{installation_id}"


def _extract_repository_name(payload: dict[str, Any]) -> str:
    repository = payload.get("repository") or {}
    if full_name := repository.get("full_name"):
        return str(full_name)
    if name := repository.get("name"):
        return str(name)
    return "unknown-repository"


def _extract_pull_request_number(payload: dict[str, Any]) -> int | None:
    pull_request = payload.get("pull_request") or {}
    if number := pull_request.get("number"):
        return int(number)
    return None


def _extract_commit_sha(payload: dict[str, Any]) -> str | None:
    if after := payload.get("after"):
        return str(after)

    pull_request = payload.get("pull_request") or {}
    head = pull_request.get("head") or {}
    if sha := head.get("sha"):
        return str(sha)

    return None


def _extract_diff_payload(payload: dict[str, Any]) -> str:
    if isinstance(payload.get("diff"), str):
        return payload["diff"]
    if isinstance(payload.get("diff_payload"), str):
        return payload["diff_payload"]
    return ""


def _get_or_create_organization(
    session,
    *,
    installation_id: str,
    org_name: str,
) -> Organization:
    organization = session.execute(
        select(Organization).where(Organization.github_installation_id == installation_id)
    ).scalar_one_or_none()

    if organization is None:
        organization = Organization(
            org_name=org_name,
            github_installation_id=installation_id,
            author_metadata=dict(AUTHOR_METADATA_DEFAULT),
        )
        session.add(organization)
        session.flush()

    return organization


@celery_app.task(name="process_github_webhook_audit")
def process_github_webhook_audit(
    installation_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Process a GitHub webhook payload under tenant-scoped database isolation."""
    diff_payload = _extract_diff_payload(payload)
    org_name = _resolve_org_name(payload, installation_id)
    repository_name = _extract_repository_name(payload)
    pull_request_number = _extract_pull_request_number(payload)
    commit_sha = _extract_commit_sha(payload)

    engine = SecurityEngine()

    try:
        scan_result = engine.scan_diff(diff_payload)
        scan_status = "blocked" if scan_result.status == "blocked" else "passed"
        violations = scan_result.violations

        with session_scope() as session:
            organization = _get_or_create_organization(
                session,
                installation_id=installation_id,
                org_name=org_name,
            )
            set_tenant_context(session, organization.id)

            audit_log = ScanAuditLog(
                organization_id=organization.id,
                repository_name=repository_name,
                pull_request_number=pull_request_number,
                commit_sha=commit_sha,
                scan_status=scan_status,
                vulnerabilities_found=violations,
                metadata_summary={
                    "installation_id": installation_id,
                    "event_type": payload.get("action") or payload.get("event") or "webhook",
                    "violation_count": len(violations),
                    "high_risk_detected": scan_status == "blocked",
                },
                author_metadata=dict(AUTHOR_METADATA_DEFAULT),
            )
            session.add(audit_log)
            session.flush()

            result = {
                "audit_log_id": str(audit_log.id),
                "organization_id": str(organization.id),
                "repository_name": repository_name,
                "scan_status": scan_status,
                "violation_count": len(violations),
            }

        logger.info(
            "Audit completed installation_id=%s repository=%s status=%s violations=%s",
            installation_id,
            repository_name,
            scan_status,
            len(violations),
        )
        return result
    finally:
        diff_payload = ""
        del diff_payload
        gc.collect()
