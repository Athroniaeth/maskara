import json
from pathlib import Path

from piighost.vault.audit import AuditLogger


def test_appends_jsonl(tmp_path: Path) -> None:
    log = tmp_path / "audit.log"
    a = AuditLogger(log)
    a.record(op="rehydrate", token="<P:x>", caller_kind="cli", caller_pid=1234)
    a.record(op="vault_show_reveal", token="<P:x>", caller_kind="mcp", caller_pid=5678)
    lines = log.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    row = json.loads(lines[0])
    assert row["op"] == "rehydrate"
    assert row["token"] == "<P:x>"
    assert row["caller_kind"] == "cli"


def test_append_only(tmp_path: Path) -> None:
    log = tmp_path / "audit.log"
    AuditLogger(log).record(op="rehydrate", caller_kind="cli")
    AuditLogger(log).record(op="rehydrate", caller_kind="cli")
    assert len(log.read_text(encoding="utf-8").splitlines()) == 2
