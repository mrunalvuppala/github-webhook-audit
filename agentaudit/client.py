#!/usr/bin/env python3
"""AgentAuditAI Phase 1 pre-commit client.

Scans staged files by POSTing them to the AgentAuditAI scan engine.
Blocks commits when the engine reports a security issue or when offline
behavior is configured to block.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

DEFAULT_API_URL = "http://localhost:8000/v1/scan"
DEFAULT_OFFLINE_MODE = "block"
DEFAULT_TIMEOUT_SECONDS = 10
MAX_FILE_BYTES = 512_000


@dataclass(frozen=True)
class ClientConfig:
    api_url: str
    offline_mode: str
    timeout_seconds: int


def load_config() -> ClientConfig:
    offline_mode = os.getenv("AGENTAUDIT_OFFLINE_MODE", DEFAULT_OFFLINE_MODE).strip().lower()
    if offline_mode not in {"block", "warn"}:
        offline_mode = DEFAULT_OFFLINE_MODE

    timeout_raw = os.getenv("AGENTAUDIT_TIMEOUT", str(DEFAULT_TIMEOUT_SECONDS))
    try:
        timeout_seconds = max(1, int(timeout_raw))
    except ValueError:
        timeout_seconds = DEFAULT_TIMEOUT_SECONDS

    return ClientConfig(
        api_url=os.getenv("AGENTAUDIT_API_URL", DEFAULT_API_URL).strip(),
        offline_mode=offline_mode,
        timeout_seconds=timeout_seconds,
    )


def run_git(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        check=False,
        capture_output=True,
        text=True,
    )


def get_staged_file_paths() -> list[str]:
    result = run_git(["diff", "--cached", "--name-only", "--diff-filter=ACM"])
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "failed to list staged files")

    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def read_staged_file(path: str) -> str | None:
    result = subprocess.run(
        ["git", "show", f":{path}"],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        return None

    if len(result.stdout) > MAX_FILE_BYTES:
        return None

    if b"\x00" in result.stdout:
        return None

    return result.stdout.decode("utf-8", errors="replace")


def collect_staged_files() -> list[dict[str, str]]:
    files: list[dict[str, str]] = []

    for path in get_staged_file_paths():
        content = read_staged_file(path)
        if content is None:
            continue
        files.append({"path": path, "content": content})

    return files


def print_error_box(title: str, message: str) -> None:
    lines = [title, "", message]
    width = max(len(line) for line in lines) + 4
    border = "=" * width

    print(file=sys.stderr)
    print(border, file=sys.stderr)
    for line in lines:
        print(f"  {line}", file=sys.stderr)
    print(border, file=sys.stderr)
    print(file=sys.stderr)


def print_warning_box(title: str, message: str) -> None:
    lines = [title, "", message]
    width = max(len(line) for line in lines) + 4
    border = "-" * width

    print(file=sys.stderr)
    print(border, file=sys.stderr)
    for line in lines:
        print(f"  {line}", file=sys.stderr)
    print(border, file=sys.stderr)
    print(file=sys.stderr)


def post_scan_request(config: ClientConfig, payload: dict[str, Any]) -> tuple[int, dict[str, Any] | None, str | None]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        config.api_url,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=config.timeout_seconds) as response:
            status_code = response.getcode()
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        status_code = exc.code
        raw = exc.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        return 0, None, str(exc.reason)

    try:
        parsed = json.loads(raw) if raw else None
    except json.JSONDecodeError:
        return status_code, None, "scan engine returned invalid JSON"

    if not isinstance(parsed, dict):
        return status_code, None, "scan engine returned a non-object JSON payload"

    return status_code, parsed, None


def handle_offline(config: ClientConfig, detail: str) -> int:
    message = (
        f"Unable to reach AgentAuditAI scan engine at {config.api_url}.\n"
        f"Detail: {detail}\n"
        f"Offline mode: {config.offline_mode}"
    )

    if config.offline_mode == "warn":
        print_warning_box("AGENTAUDIT WARNING", message)
        return 0

    print_error_box(
        "AGENTAUDIT COMMIT BLOCKED",
        message + "\nCommit blocked because AGENTAUDIT_OFFLINE_MODE=block.",
    )
    return 1


def handle_blocked(reason: str) -> int:
    print_error_box(
        "AGENTAUDIT COMMIT BLOCKED",
        "The scan engine detected a security issue in staged files.\n" + reason,
    )
    return 1


def main() -> int:
    try:
        staged_files = collect_staged_files()
    except RuntimeError as exc:
        print_error_box("AGENTAUDIT COMMIT BLOCKED", f"Git staging inspection failed.\n{exc}")
        return 1

    if not staged_files:
        return 0

    config = load_config()
    status_code, payload, network_error = post_scan_request(config, {"files": staged_files})

    if network_error is not None:
        return handle_offline(config, network_error)

    if status_code != 200:
        detail = f"Scan engine returned HTTP {status_code}."
        if payload and payload.get("reason"):
            detail += f"\nReason: {payload['reason']}"
        return handle_blocked(detail)

    if payload and payload.get("status") == "blocked":
        reason = str(payload.get("reason") or "Security policy violation detected.")
        return handle_blocked(reason)

    return 0


if __name__ == "__main__":
    sys.exit(main())
