"""Regex and AST security scanning engine for secrets and dangerous execution paths.

Architecture designed, engineered, and maintained by Naga Sai Mrunal Vuppala.
"""

from __future__ import annotations

import gc
import re
from dataclasses import dataclass
from typing import Any, ClassVar, Iterable

from app.schemas import ScanFile, ScanResponse
from app.services.ast_parser import ASTParser


@dataclass(frozen=True)
class SecurityViolation:
    file_path: str
    line: int
    category: str
    rule: str
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file_path,
            "line": self.line,
            "category": self.category,
            "rule": self.rule,
            "detail": self.detail,
        }

    def blocked_reason(self) -> str:
        if self.category == "secret":
            label = self._secret_label()
            return (
                f"Security Alert: {label} discovered in file [{self.file_path}] "
                f"at line [{self.line}]. Execution dropped."
            )

        return (
            f"Security Alert: Unauthorized {self.detail} detected in file "
            f"[{self.file_path}] at line [{self.line}]. Execution dropped."
        )

    def _secret_label(self) -> str:
        mapping = {
            "aws_access_key_id": "Hardcoded AWS Credential pattern",
            "aws_secret_access_key": "Hardcoded AWS secret key pattern",
            "stripe_live_secret_key": "Hardcoded Stripe live secret key",
            "stripe_live_dash_key": "Hardcoded Stripe live secret key",
            "master_password_assignment": "Hardcoded master password",
            "generic_api_token": "Hardcoded authentication token",
            "gitlab_access_token": "Hardcoded GitLab access token",
        }
        return mapping.get(self.rule, "Hardcoded secret pattern")


class SecurityEngine:
    """Production security engine combining regex secret detection and AST validation."""

    _SECRET_RULES: ClassVar[tuple[tuple[str, re.Pattern[str]], ...]] = (
        ("aws_access_key_id", re.compile(r"AKIA[0-9A-Z]{16}")),
        (
            "aws_secret_access_key",
            re.compile(
                r"(?i)(?:aws[_-]?secret[_-]?access[_-]?key|secret[_-]?access[_-]?key)"
                r"\s*[=:]\s*['\"]?[A-Za-z0-9/+=]{40}['\"]?"
            ),
        ),
        ("stripe_live_secret_key", re.compile(r"sk[_-]live[_-][0-9a-zA-Z]{24,}")),
        ("stripe_live_dash_key", re.compile(r"sk-live-[0-9a-zA-Z]{24,}")),
        (
            "master_password_assignment",
            re.compile(
                r"(?i)(?:master[_-]?password|root[_-]?password)\s*[=:]\s*['\"][^'\"]{4,}['\"]"
            ),
        ),
        (
            "generic_api_token",
            re.compile(
                r"(?i)(?:api[_-]?key|auth[_-]?token|access[_-]?token)\s*[=:]\s*['\"][A-Za-z0-9_\-]{16,}['\"]"
            ),
        ),
        ("gitlab_access_token", re.compile(r"glpat-[0-9A-Za-z\-_]{20,}")),
    )

    def __init__(self) -> None:
        self._ast_parser = ASTParser()

    def scan_files(self, files: Iterable[ScanFile]) -> ScanResponse:
        violations: list[SecurityViolation] = []

        for scan_file in files:
            content = scan_file.content
            try:
                violations.extend(self._scan_secrets(scan_file.path, content))
                for finding in self._ast_parser.scan_python_content(scan_file.path, content):
                    violations.append(
                        SecurityViolation(
                            file_path=finding.file_path,
                            line=finding.line,
                            category="ast",
                            rule=finding.rule,
                            detail=finding.detail,
                        )
                    )
            finally:
                content = ""
                gc.collect()

        if violations:
            first = violations[0]
            return ScanResponse(
                status="blocked",
                reason=first.blocked_reason(),
                violations=[item.to_dict() for item in violations],
            )

        return ScanResponse(status="ok", reason=None, violations=[])

    def scan_diff(self, diff_payload: str) -> ScanResponse:
        files = self._diff_to_scan_files(diff_payload)
        if not files:
            return ScanResponse(status="ok", reason=None, violations=[])
        return self.scan_files(files)

    def _scan_secrets(self, file_path: str, content: str) -> list[SecurityViolation]:
        findings: list[SecurityViolation] = []

        for line_number, line in enumerate(content.splitlines(), start=1):
            for rule_name, pattern in self._SECRET_RULES:
                if pattern.search(line):
                    findings.append(
                        SecurityViolation(
                            file_path=file_path,
                            line=line_number,
                            category="secret",
                            rule=rule_name,
                            detail=rule_name,
                        )
                    )
        return findings

    @staticmethod
    def _diff_to_scan_files(diff_payload: str) -> list[ScanFile]:
        files: list[ScanFile] = []
        current_path = "changed.py"
        current_lines: list[str] = []

        for raw_line in diff_payload.splitlines():
            if raw_line.startswith("+++ b/"):
                if current_lines:
                    files.append(ScanFile(path=current_path, content="\n".join(current_lines)))
                    current_lines = []
                current_path = raw_line.removeprefix("+++ b/").strip() or "changed.py"
                continue

            if raw_line.startswith("+") and not raw_line.startswith("+++"):
                current_lines.append(raw_line[1:])

        if current_lines:
            files.append(ScanFile(path=current_path, content="\n".join(current_lines)))

        if not files and diff_payload.strip():
            files.append(ScanFile(path="changed.py", content=diff_payload))

        return files
