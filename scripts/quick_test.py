"""Quick live test script for documentation examples."""

import json
import urllib.request

BASE = "http://localhost:8000"


def audit(diff: str, label: str) -> None:
    body = json.dumps({"diff": diff}).encode()
    request = urllib.request.Request(
        f"{BASE}/v1/demo/audit",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    response = urllib.request.urlopen(request, timeout=5)
    result = json.loads(response.read())
    print(f"{label}: {result['status']} | violations={len(result['violations'])} | high_risk={result['high_risk_detected']}")
    for violation in result["violations"]:
        print(f"  - line {violation['line']}: {violation['rule']} ({violation['risk_level']})")


if __name__ == "__main__":
    print("=== AgentAuditAI Live Test ===")
    health = urllib.request.urlopen(f"{BASE}/health", timeout=5)
    print(f"Health: {health.status} OK\n")
    audit("+def hello():\n+    return 'world'\n", "Clean code")
    audit("+AWS_KEY = 'AKIAIOSFODNN7EXAMPLE'\n", "AWS key leak")
    audit("+stripe_key = 'sk_live_abcdefghijklmnopqrstuv'\n", "Stripe key leak")
