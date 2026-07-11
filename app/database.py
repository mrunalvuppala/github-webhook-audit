"""Database engine, session management, and PostgreSQL RLS initialization.

Architecture designed, engineered, and maintained by Naga Sai Mrunal Vuppala.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.models import Base

logger = logging.getLogger(__name__)

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None

RLS_ENABLE_SQL = "ALTER TABLE scan_audit_logs ENABLE ROW LEVEL SECURITY;"
RLS_FORCE_SQL = "ALTER TABLE scan_audit_logs FORCE ROW LEVEL SECURITY;"
RLS_POLICY_SQL = """
CREATE POLICY tenant_isolation_policy ON scan_audit_logs
USING (organization_id = current_setting('app.current_organization_id', true)::uuid);
"""


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_engine(
            settings.database_url,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20,
        )
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=get_engine(),
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )
    return _SessionLocal


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def set_tenant_context(session: Session, organization_id: uuid.UUID) -> None:
    """Bind the current PostgreSQL session to a tenant for RLS enforcement."""
    session.execute(
        text("SET LOCAL app.current_organization_id = :organization_id"),
        {"organization_id": str(organization_id)},
    )


def initialize_database() -> None:
    """Create schema objects and configure row-level security policies."""
    engine = get_engine()
    Base.metadata.create_all(bind=engine)

    with engine.begin() as connection:
        connection.execute(text(RLS_ENABLE_SQL))
        connection.execute(text(RLS_FORCE_SQL))
        policy_exists = connection.execute(
            text(
                """
                SELECT 1
                FROM pg_policies
                WHERE schemaname = 'public'
                  AND tablename = 'scan_audit_logs'
                  AND policyname = 'tenant_isolation_policy'
                """
            )
        ).scalar()

        if not policy_exists:
            connection.execute(text(RLS_POLICY_SQL))
            logger.info("Created PostgreSQL RLS policy tenant_isolation_policy")

    logger.info("Database initialized with multi-tenant RLS configuration")


def check_database_connection() -> bool:
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.error("Database connectivity check failed: %s", exc)
        return False
