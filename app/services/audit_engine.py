"""Stateless diff auditor for hardcoded credential detection."""

from __future__ import annotations

import gc
import re
from typing import Any, ClassVar

from pydantic import BaseModel, Field


class AuditResult(BaseModel):
    """Outcome of a single diff inspection pass."""

    status: str = Field(description='Audit verdict: "PASS" or "FAIL".')
    violations: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Detected policy violations with line, rule, and risk level.",
    )
    high_risk_detected: bool = Field(
        description="True when at least one violation is classified as high risk.",
    )


class StatelessAuditEngine:
    """Regex-driven credential scanner that never retains inspected diff content."""

    _CREDENTIAL_RULES: ClassVar[tuple[tuple[str, re.Pattern[str], str], ...]] = (
        (
            "aws_access_key_id",
            re.compile(r"AKIA[0-9A-Z]{16}"),
            "high",
        ),
        (
            "aws_secret_access_key",
            re.compile(
                r"(?i)(?:aws[_-]?secret[_-]?access[_-]?key|secret[_-]?access[_-]?key)"
                r"\s*[=:]\s*['\"]?[A-Za-z0-9/+=]{40}['\"]?"
            ),
            "high",
        ),
        (
            "stripe_live_secret_key",
            re.compile(r"sk_live_[0-9a-zA-Z]{24,}"),
            "high",
        ),
        (
            "stripe_live_restricted_key",
            re.compile(r"rk_live_[0-9a-zA-Z]{24,}"),
            "high",
        ),
        (
            "stripe_test_secret_key",
            re.compile(r"sk_test_[0-9a-zA-Z]{24,}"),
            "medium",
        ),
        (
            "gitlab_access_token",
            re.compile(r"glpat-[0-9A-Za-z\-_]{20,}"),
            "high",
        ),
    )

    def inspect_diff(self, diff_content: str) -> AuditResult:
        """Scan a unified diff for hardcoded credentials without retaining its content."""
        lines: list[str] | None = None
        violations: list[dict[str, Any]] = []

        try:
            lines = diff_content.splitlines()

            for line_number, raw_line in enumerate(lines, start=1):
                if not raw_line.startswith("+") or raw_line.startswith("+++"):
                    continue

                added_line = raw_line[1:]
                for rule_name, pattern, risk_level in self._CREDENTIAL_RULES:
                    if pattern.search(added_line):
                        violations.append(
                            {
                                "line": line_number,
                                "rule": rule_name,
                                "risk_level": risk_level,
                            }
                        )

            high_risk_detected = any(
                violation["risk_level"] == "high" for violation in violations
            )
            status = "FAIL" if violations else "PASS"

            return AuditResult(
                status=status,
                violations=violations,
                high_risk_detected=high_risk_detected,
            )
        finally:
            if lines is not None:
                for index in range(len(lines)):
                    lines[index] = ""
                lines.clear()

            diff_content = ""
            del lines
            del diff_content
            gc.collect()
