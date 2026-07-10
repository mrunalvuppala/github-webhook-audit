"""Application configuration loaded from environment variables."""

from __future__ import annotations

import re
import sys
from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEV_DATABASE_PATTERNS = (
    re.compile(r"localhost", re.IGNORECASE),
    re.compile(r"127\.0\.0\.1"),
    re.compile(r"sqlite", re.IGNORECASE),
    re.compile(r":memory:", re.IGNORECASE),
    re.compile(r"/test\b", re.IGNORECASE),
    re.compile(r"_test\b", re.IGNORECASE),
    re.compile(r"\.local\b", re.IGNORECASE),
)


class Settings(BaseSettings):
    """Central configuration for Redis, webhooks, database caching, and memory limits."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    redis_url: str = Field(
        default="redis://localhost:6379/0",
        validation_alias="REDIS_URL",
        description="Redis connection URL for caching and pub/sub.",
    )
    github_webhook_secret: SecretStr = Field(
        validation_alias="GITHUB_WEBHOOK_SECRET",
        description="HMAC secret used to verify GitHub webhook signatures.",
    )
    database_url: str = Field(
        validation_alias="DATABASE_URL",
        description="Database URL for tenant configuration caching.",
    )
    memory_retention_limit_mb: int = Field(
        default=50,
        ge=1,
        validation_alias="MEMORY_RETENTION_LIMIT_MB",
        description="Maximum memory footprint (MB) retained while parsing payloads.",
    )
    environment: Literal["development", "staging", "production"] = Field(
        default="development",
        validation_alias="ENVIRONMENT",
        description="Runtime environment used for safety checks and logging.",
    )

    @field_validator("github_webhook_secret", mode="before")
    @classmethod
    def _reject_empty_webhook_secret(cls, value: object) -> object:
        if value is None or (isinstance(value, str) and not value.strip()):
            raise ValueError("GITHUB_WEBHOOK_SECRET must be a non-empty secret string")
        return value

    @field_validator("database_url", mode="before")
    @classmethod
    def _reject_empty_database_url(cls, value: object) -> object:
        if value is None or (isinstance(value, str) and not value.strip()):
            raise ValueError("DATABASE_URL must be set for tenant configuration caching")
        return value

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    @property
    def is_production_database_url(self) -> bool:
        return not any(pattern.search(self.database_url) for pattern in _DEV_DATABASE_PATTERNS)

    def warn_if_dev_without_production_database(self) -> None:
        """Emit a safe console warning when dev mode uses a non-production database."""
        if self.is_development and not self.is_production_database_url:
            message = (
                "WARNING: Running in development mode without a production DATABASE_URL. "
                "Tenant configuration caching is using a local or non-production database."
            )
            print(message, file=sys.stderr)


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance and run startup safety checks once."""
    settings = Settings()
    settings.warn_if_dev_without_production_database()
    return settings
