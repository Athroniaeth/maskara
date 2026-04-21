"""Per-session append-only audit log for hacienda redaction events.

Records each anonymize/rehydrate call plus metadata (timestamp, event name,
payload). Payloads MUST NOT contain raw PII — callers pass placeholders and
vault tokens only. This is a safety-critical invariant; we document it in
tests but cannot enforce it structurally without taking a dependency on the
vault encryption layer.

Storage: ``<root>/sessions/<session_id>.audit.jsonl``. JSONL so partial
writes never corrupt prior events.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


class SessionAudit:
    def __init__(self, *, root: Path, session_id: str) -> None:
        if not _SESSION_ID_RE.match(session_id):
            raise ValueError(f"invalid session id: {session_id!r}")
        self._file = root / "sessions" / f"{session_id}.audit.jsonl"
        self._file.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: str, payload: dict[str, Any]) -> None:
        """Append a single event line. Raises TypeError on non-serialisable payloads."""
        record = {
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "event": event,
            "payload": payload,
        }
        # json.dumps raises TypeError for non-serialisable values — we let it propagate.
        line = json.dumps(record, ensure_ascii=False)
        with self._file.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def read(self) -> list[dict[str, Any]]:
        if not self._file.exists():
            return []
        out: list[dict[str, Any]] = []
        with self._file.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
        return out
