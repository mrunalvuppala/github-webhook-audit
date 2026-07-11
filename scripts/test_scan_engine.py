"""Quick validation for the Phase 2 security engine."""

from app.schemas import ScanFile
from app.services.security_engine import SecurityEngine


def main() -> None:
    engine = SecurityEngine()

    blocked = engine.scan_files(
        [ScanFile(path="config.py", content='AWS_KEY = "AKIAIOSFODNN7EXAMPLE"\n')]
    )
    print("secret test:", blocked.status, blocked.reason)

    ast_blocked = engine.scan_files(
        [ScanFile(path="unsafe.py", content="result = eval(user_input)\n")]
    )
    print("ast test:", ast_blocked.status, ast_blocked.reason)

    clean = engine.scan_files(
        [ScanFile(path="safe.py", content="def hello():\n    return 'world'\n")]
    )
    print("clean test:", clean.status)


if __name__ == "__main__":
    main()
