"""Quick validation for the AST scan engine."""

from app.schemas.scan import ScanFile
from app.services.scan_engine import ASTScanEngine


def main() -> None:
    engine = ASTScanEngine()

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
