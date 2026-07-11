"""Tree-sitter and AST parsing utilities for Python security analysis.

Architecture designed, engineered, and maintained by Naga Sai Mrunal Vuppala.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import ClassVar

try:
    import tree_sitter_python as tspython
    from tree_sitter import Language, Parser

    _PY_LANGUAGE = Language(tspython.language())
    _TREE_SITTER_AVAILABLE = True
except ImportError:
    _PY_LANGUAGE = None
    _TREE_SITTER_AVAILABLE = False


@dataclass(frozen=True)
class ASTFinding:
    file_path: str
    line: int
    rule: str
    detail: str

    def to_dict(self) -> dict[str, str | int]:
        return {
            "file": self.file_path,
            "line": self.line,
            "category": "ast",
            "rule": self.rule,
            "detail": self.detail,
        }


class ASTParser:
    """Grammar-aware Python AST inspector with optional tree-sitter acceleration."""

    _CALL_NAMES: ClassVar[frozenset[str]] = frozenset(
        {"eval", "exec", "__import__", "compile", "system", "popen", "spawn", "run"}
    )

    _ATTRIBUTE_CHAINS: ClassVar[tuple[tuple[tuple[str, ...], str], ...]] = (
        (("os", "system"), "os.system"),
        (("os", "popen"), "os.popen"),
        (("subprocess", "call"), "subprocess.call"),
        (("subprocess", "run"), "subprocess.run"),
        (("subprocess", "Popen"), "subprocess.Popen"),
    )

    def scan_python_content(self, file_path: str, content: str) -> list[ASTFinding]:
        if not self._is_python_file(file_path):
            return []

        if _TREE_SITTER_AVAILABLE and _PY_LANGUAGE is not None:
            if not self._tree_sitter_syntax_valid(content):
                return []

        try:
            module = ast.parse(content, filename=file_path)
        except SyntaxError:
            return []

        findings: list[ASTFinding] = []
        for node in ast.walk(module):
            finding = self._inspect_node(file_path, node)
            if finding is not None:
                findings.append(finding)
        return findings

    def _tree_sitter_syntax_valid(self, content: str) -> bool:
        if _PY_LANGUAGE is None:
            return True

        parser = Parser(_PY_LANGUAGE)
        tree = parser.parse(content.encode("utf-8"))
        return not tree.root_node.has_error

    def _inspect_node(self, file_path: str, node: ast.AST) -> ASTFinding | None:
        line_number = getattr(node, "lineno", None)
        if line_number is None or not isinstance(node, ast.Call):
            return None

        direct_name = self._resolve_call_name(node.func)
        if direct_name in self._CALL_NAMES:
            return ASTFinding(
                file_path=file_path,
                line=line_number,
                rule="dangerous_call",
                detail=f"{direct_name}() execution",
            )

        attribute_name = self._resolve_attribute_chain(node.func)
        for chain, label in self._ATTRIBUTE_CHAINS:
            if attribute_name == chain:
                return ASTFinding(
                    file_path=file_path,
                    line=line_number,
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
