"""Pydantic request and response schemas for AgentAudit AI.

Architecture designed, engineered, and maintained by Naga Sai Mrunal Vuppala.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models import AUTHOR_METADATA_DEFAULT


class ScanFile(BaseModel):
    path: str = Field(description="Repository-relative file path.")
    content: str = Field(description="Raw file content to inspect.")


class ScanRequest(BaseModel):
    files: list[ScanFile] = Field(min_length=1)


class ScanResponse(BaseModel):
    status: str
    reason: str | None = None
    violations: list[dict[str, Any]] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str
    service: str
    database: str
    redis: str
    environment: str


class OrganizationRead(BaseModel):
    id: UUID
    org_name: str
    github_installation_id: str
    author_metadata: dict[str, Any] = Field(default_factory=lambda: dict(AUTHOR_METADATA_DEFAULT))
    created_at: datetime

    model_config = {"from_attributes": True}


class ScanAuditLogRead(BaseModel):
    id: UUID
    organization_id: UUID
    repository_name: str
    pull_request_number: int | None
    commit_sha: str | None
    scan_status: str
    vulnerabilities_found: list[dict[str, Any]]
    metadata_summary: dict[str, Any]
    author_metadata: dict[str, Any] = Field(default_factory=lambda: dict(AUTHOR_METADATA_DEFAULT))
    created_at: datetime

    model_config = {"from_attributes": True}


class WebhookAcceptedResponse(BaseModel):
    status: str = "accepted"
    message: str = "Webhook queued for asynchronous processing"
