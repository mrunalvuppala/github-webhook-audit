"""High-performance AST and secret scanning engine for pre-commit and CI pipelines."""

from __future__ import annotations

import ast
import gc
import re
from dataclasses import dataclass
from typing import Any, ClassVar, Iterable

from app.schemas.scan import ScanFile, ScanResponse

# Optional tree-sitter acceleration for Python grammar-aware parsing.
try:
    import tree_sitter_python as tspython
    from tree_sitter import Language, Parser

    _PY_LANGUAGE = Language(tspython.language())
    _TREE_SITTER_AVAILABLE = True
except ImportError:
    _PY_LANGUAGE = None
    _TREE_SITTER_AVAILABLE = False


@dataclass(frozen=True)
class ScanViolation:
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


class ASTScanEngine:
    """Closed-source scan worker combining regex secret detection and AST safety checks."""

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
            re.compile(r"(?i)(?:master[_-]?password|root[_-]?password)\s*[=:]\s*['\"][^'\"]{4,}['\"]"),
        ),
        (
            "generic_api_token",
            re.compile(r"(?i)(?:api[_-]?key|auth[_-]?token|access[_-]?token)\s*[=:]\s*['\"][A-Za-z0-9_\-]{16,}['\"]"),
        ),
        ("gitlab_access_token", re.compile(r"glpat-[0-9A-Za-z\-_]{20,}")),
    )

    _AST_CALL_NAMES: ClassVar[frozenset[str]] = frozenset(
        {"eval", "exec", "__import__", "compile", "system", "popen", "spawn", "run"}
    )

    _AST_ATTRIBUTE_CHAINS: ClassVar[tuple[tuple[str, ...], str], ...] = (
        (("os", "system"), "os.system"),
        (("os", "popen"), "os.popen"),
        (("subprocess", "call"), "subprocess.call"),
        (("subprocess", "run"), "subprocess.run"),
        (("subprocess", "Popen"), "subprocess.Popen"),
    )

    def scan_files(self, files: Iterable[ScanFile]) -> ScanResponse:
        violations: list[ScanViolation] = []

        for scan_file in files:
            content = scan_file.content
            try:
                violations.extend(self._scan_secrets(scan_file.path, content))
                if self._is_python_file(scan_file.path):
                    violations.extend(self._scan_ast(scan_file.path, content))
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

    def _scan_secrets(self, file_path: str, content: str) -> list[ScanViolation]:
        findings: list[ScanViolation] = []

        for line_number, line in enumerate(content.splitlines(), start=1):
            for rule_name, pattern in self._SECRET_RULES:
                if pattern.search(line):
                    findings.append(
                        ScanViolation(
                            file_path=file_path,
                            line=line_number,
                            category="secret",
                            rule=rule_name,
                            detail=rule_name,
                        )
                    )
        return findings

    def _scan_ast(self, file_path: str, content: str) -> list[ScanViolation]:
        if _TREE_SITTER_AVAILABLE and _PY_LANGUAGE is not None:
            syntax_valid = self._tree_sitter_syntax_valid(content)
            if not syntax_valid:
                return []

        try:
            module = ast.parse(content, filename=file_path)
        except SyntaxError:
            return []

        findings: list[ScanViolation] = []
        for node in ast.walk(module):
            finding = self._inspect_ast_node(file_path, node)
            if finding is not None:
                findings.append(finding)
        return findings

    def _tree_sitter_syntax_valid(self, content: str) -> bool:
        if _PY_LANGUAGE is None:
            return True

        parser = Parser(_PY_LANGUAGE)
        tree = parser.parse(content.encode("utf-8"))
        root = tree.root_node
        return not root.has_error

    def _inspect_ast_node(self, file_path: str, node: ast.AST) -> ScanViolation | None:
        line_number = getattr(node, "lineno", None)
        if line_number is None:
            return None

        if isinstance(node, ast.Call):
            direct_name = self._resolve_call_name(node.func)
            if direct_name in self._AST_CALL_NAMES:
                return ScanViolation(
                    file_path=file_path,
                    line=line_number,
                    category="ast",
                    rule="dangerous_call",
                    detail=f"{direct_name}() execution",
                )

            attribute_name = self._resolve_attribute_chain(node.func)
            for chain, label in self._AST_ATTRIBUTE_CHAINS:
                if attribute_name == chain:
                    return ScanViolation(
                        file_path=file_path,
                        line=line_number,
                        category="ast",
                        rule="dangerous_call",
                        detail=f"{label} execution",
                    )

        return None

    @staticmethod
    def _resolve_call_name(func: ast.AST) -> str | None:
        if isinstance(func, ast.Name):
            return func.id
        return None

    @staticmethod
    def _resolve_attribute_chain(node: ast.AST) -> tuple[str, ...] | None:
        parts: list[str] = []
        current: ast.AST | None = node

        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value

        if isinstance(current, ast.Name):
            parts.append(current.id)
            return tuple(reversed(parts))

        return None

    @staticmethod
    def _is_python_file(path: str) -> bool:
        lowered = path.lower()
        return lowered.endswith(".py") or lowered.endswith(".pyw")
