#!/usr/bin/env python3
"""Live demo script for presenting the GitHub webhook audit platform."""

from __future__ import annotations

import hashlib
import hmac
import json
import sys
import time
import urllib.error
import urllib.request

API_URL = "http://localhost:8000"
WEBHOOK_URL = f"{API_URL}/v1/webhooks/github"
SECRET = "replace-with-your-webhook-secret"


def wait_for_api(timeout: int = 60) -> bool:
    print("Waiting for API to start", end="", flush=True)
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{API_URL}/health", timeout=2) as response:
                if response.status == 200:
                    print(" OK")
                    return True
        except (urllib.error.URLError, TimeoutError):
            print(".", end="", flush=True)
            time.sleep(2)
    print(" TIMEOUT")
    return False


def send_webhook(label: str, diff: str, tenant_id: str = "demo-tenant") -> None:
    payload = {
        "tenant_id": tenant_id,
        "installation": {"id": 4242, "account": {"login": "mrunalvuppala"}},
        "diff": diff,
    }
    body = json.dumps(payload).encode()
    signature = (
        "sha256="
        + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    )

    request = urllib.request.Request(
        WEBHOOK_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": signature,
        },
        method="POST",
    )

    print(f"\n--- Demo: {label} ---")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            print(f"  HTTP {response.status} Accepted")
            print("  Webhook queued for background audit.")
    except urllib.error.HTTPError as exc:
        print(f"  HTTP {exc.code} {exc.reason}")
        print(f"  {exc.read().decode()}")


def main() -> int:
    print()
    print("=" * 50)
    print("  AgentAuditAI - Live Presentation Demo")
    print("=" * 50)

    if not wait_for_api():
        print("\nStart the app first:  start.bat")
        return 1

    send_webhook(
        "Clean code (should PASS)",
        "+def hello():\n+    return 'world'\n",
    )
    send_webhook(
        "Leaked AWS key (should FAIL)",
        "+AWS_KEY = 'AKIAIOSFODNN7EXAMPLE'\n",
    )
    send_webhook(
        "Leaked Stripe key (should FAIL)",
        "+stripe_key = 'sk_live_abcdefghijklmnopqrstuv'\n",
    )

    print("\n" + "=" * 50)
    print("  Demo complete!")
    print("  Check the worker terminal for audit results.")
    print("  Open http://localhost:8000/docs for the API UI.")
    print("=" * 50)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
