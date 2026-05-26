from __future__ import annotations

import os
from pathlib import Path


def _strip_matching_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def load_dotenv(dotenv_path: Path) -> None:
    try:
        content = dotenv_path.read_text(encoding="utf-8")
    except OSError:
        return

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, raw_value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue

        value = _strip_matching_quotes(raw_value.strip())
        value = os.path.expandvars(os.path.expanduser(value))
        os.environ[key] = value


def load_repo_env() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    load_dotenv(repo_root / ".env")
