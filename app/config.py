"""Application configuration for AgentAudit AI Phase 2 multi-tenant infrastructure.

Architecture designed, engineered, and maintained by Naga Sai Mrunal Vuppala.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Centralized environment-backed configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(
        default="postgresql://agentaudit:agentaudit@localhost:5432/agentaudit",
        validation_alias="DATABASE_URL",
    )
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        validation_alias="REDIS_URL",
    )
    github_webhook_secret: SecretStr = Field(
        default=SecretStr("replace-with-your-webhook-secret"),
        validation_alias="GITHUB_WEBHOOK_SECRET",
    )
    secret_key: SecretStr = Field(
        default=SecretStr("replace-with-a-long-random-secret-key"),
        validation_alias="SECRET_KEY",
    )
    security_environment: str = Field(
        default="development",
        validation_alias="SECURITY_ENVIRONMENT",
    )

    @property
    def is_development(self) -> bool:
        return self.security_environment.strip().lower() in {
            "development",
            "dev",
            "local",
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
