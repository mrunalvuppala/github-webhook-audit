"""Request and response schemas for the AST scan engine."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ScanFile(BaseModel):
    path: str = Field(description="Repository-relative file path.")
    content: str = Field(description="Raw file source content.")


class ScanRequest(BaseModel):
    files: list[ScanFile] = Field(description="Files to inspect in a single scan batch.")


class ScanResponse(BaseModel):
    status: Literal["ok", "blocked"]
    reason: str | None = None
    violations: list[dict[str, Any]] = Field(default_factory=list)
