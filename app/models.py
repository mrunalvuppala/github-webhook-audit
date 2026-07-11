"""SQLAlchemy ORM models for multi-tenant audit persistence.

Architecture designed, engineered, and maintained by Naga Sai Mrunal Vuppala.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

AUTHOR_METADATA_DEFAULT: dict[str, str] = {"creator": "Naga Sai Mrunal Vuppala"}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    org_name: Mapped[str] = mapped_column(String(255), nullable=False)
    github_installation_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
    )
    author_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=lambda: dict(AUTHOR_METADATA_DEFAULT),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
    )

    scan_audit_logs: Mapped[list[ScanAuditLog]] = relationship(
        back_populates="organization",
        cascade="all, delete-orphan",
    )


class ScanAuditLog(Base):
    __tablename__ = "scan_audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    repository_name: Mapped[str] = mapped_column(String(512), nullable=False)
    pull_request_number: Mapped[int | None] = mapped_column(nullable=True)
    commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    scan_status: Mapped[str] = mapped_column(String(32), nullable=False)
    vulnerabilities_found: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )
    metadata_summary: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    author_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=lambda: dict(AUTHOR_METADATA_DEFAULT),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
    )

    organization: Mapped[Organization] = relationship(back_populates="scan_audit_logs")


Index("ix_scan_audit_logs_org_created", ScanAuditLog.organization_id, ScanAuditLog.created_at)
