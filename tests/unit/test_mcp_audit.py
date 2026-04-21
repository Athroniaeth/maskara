"""Per-session append-only audit log."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from piighost.mcp.audit import SessionAudit


class TestSessionAudit:
    def test_append_writes_jsonl(self, tmp_path: Path) -> None:
        audit = SessionAudit(root=tmp_path, session_id="sess-1")
        audit.append("anonymize", {"doc": "a.pdf", "n_entities": 3})
        audit.append("rehydrate", {"tokens": ["PER_001"]})
        file = tmp_path / "sessions" / "sess-1.audit.jsonl"
        assert file.exists()
        lines = file.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2
        first = json.loads(lines[0])
        assert first["event"] == "anonymize"
        assert first["payload"] == {"doc": "a.pdf", "n_entities": 3}
        assert "timestamp" in first

    def test_read_returns_parsed_events(self, tmp_path: Path) -> None:
        audit = SessionAudit(root=tmp_path, session_id="sess-2")
        audit.append("anonymize", {"n": 1})
        audit.append("anonymize", {"n": 2})
        events = audit.read()
        assert [e["payload"]["n"] for e in events] == [1, 2]

    def test_read_empty_session_returns_empty_list(self, tmp_path: Path) -> None:
        audit = SessionAudit(root=tmp_path, session_id="never-used")
        assert audit.read() == []

    def test_append_refuses_nonserialisable(self, tmp_path: Path) -> None:
        audit = SessionAudit(root=tmp_path, session_id="sess-3")
        with pytest.raises(TypeError):
            audit.append("event", {"bad": object()})

    def test_session_id_validated(self, tmp_path: Path) -> None:
        # No path traversal via session id.
        with pytest.raises(ValueError):
            SessionAudit(root=tmp_path, session_id="../etc/passwd")

    def test_append_never_logs_raw_pii_values(self, tmp_path: Path) -> None:
        """Safety invariant: the audit payload must not contain raw PII.

        Callers pass placeholders + vault tokens only. This test documents
        the contract — the audit module doesn't enforce it (can't), but any
        future contributor grepping for 'test_append_never_logs_raw_pii' will
        be reminded.
        """
        audit = SessionAudit(root=tmp_path, session_id="sess-4")
        audit.append("anonymize", {"placeholder": "«PER_001»", "token": "tok_abc"})
        events = audit.read()
        assert events[0]["payload"]["placeholder"] == "«PER_001»"
