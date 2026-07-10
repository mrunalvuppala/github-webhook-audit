"""Celery worker tasks for asynchronous audit processing."""

from __future__ import annotations

import gc
import logging
from typing import Any
from uuid import uuid4

from celery import Celery

from app.core.config import get_settings
from app.services.audit_engine import StatelessAuditEngine

logger = logging.getLogger(__name__)

settings = get_settings()

celery_app = Celery(
    "app",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)


def _record_audit_result(
    *,
    tenant_id: str,
    installation_id: str,
    status: str,
    violation_count: int,
    high_risk_detected: bool,
) -> dict[str, Any]:
    """Mock callback that persists audit metadata to the tenant configuration store."""
    record = {
        "record_id": str(uuid4()),
        "tenant_id": tenant_id,
        "installation_id": installation_id,
        "status": status,
        "violation_count": violation_count,
        "high_risk_detected": high_risk_detected,
        "persisted": True,
    }
    logger.info(
        "Recorded audit metadata tenant_id=%s installation_id=%s record_id=%s status=%s violation_count=%s",
        tenant_id,
        installation_id,
        record["record_id"],
        status,
        violation_count,
    )
    return record


@celery_app.task(name="execute_asynchronous_audit")
def execute_asynchronous_audit(
    tenant_id: str,
    installation_id: str,
    diff_payload: str,
) -> dict[str, Any]:
    """Run a stateless diff audit in the background and persist metadata only."""
    engine = StatelessAuditEngine()

    try:
        audit_result = engine.inspect_diff(diff_payload)
        violation_count = len(audit_result.violations)

        logger.info(
            "Audit completed tenant_id=%s installation_id=%s status=%s violation_count=%s high_risk_detected=%s",
            tenant_id,
            installation_id,
            audit_result.status,
            violation_count,
            audit_result.high_risk_detected,
        )

        return _record_audit_result(
            tenant_id=tenant_id,
            installation_id=installation_id,
            status=audit_result.status,
            violation_count=violation_count,
            high_risk_detected=audit_result.high_risk_detected,
        )
    finally:
        diff_payload = ""
        del diff_payload
        gc.collect()
