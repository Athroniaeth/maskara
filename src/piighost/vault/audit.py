"""Append-only JSONL audit log for sensitive vault operations."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


class AuditLogger:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def record(
        self,
        *,
        op: str,
        token: str | None = None,
        caller_kind: str = "cli",
        caller_pid: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        row = {
            "ts": int(time.time()),
            "op": op,
            "token": token,
            "caller_kind": caller_kind,
            "caller_pid": caller_pid,
            "metadata": metadata or {},
        }
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
