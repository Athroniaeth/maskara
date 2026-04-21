"""backup.sh and restore.sh round-trip a volume's contents."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

BACKUP = Path("docker/scripts/backup.sh").resolve()
RESTORE = Path("docker/scripts/restore.sh").resolve()


def _has_tools() -> bool:
    return all(shutil.which(t) for t in ("bash", "tar", "age"))


pytestmark = pytest.mark.skipif(
    not _has_tools(), reason="bash/tar/age not available"
)


def test_backup_restore_roundtrip(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "vault").mkdir()
    (data_dir / "vault" / "store.db").write_bytes(b"encrypted-payload")
    (data_dir / "audit").mkdir()
    (data_dir / "audit" / "log").write_text("entry 1\nentry 2\n")

    key_path = tmp_path / "age.key"
    subprocess.run(
        ["age-keygen", "-o", str(key_path)],
        check=True,
        capture_output=True,
    )
    recipient = subprocess.run(
        ["age-keygen", "-y", str(key_path)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    recipient_file = tmp_path / "recipient.txt"
    recipient_file.write_text(recipient)

    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()

    result = subprocess.run(
        ["bash", str(BACKUP)],
        env={
            **os.environ,
            "PIIGHOST_DATA_DIR": str(data_dir),
            "PIIGHOST_AGE_RECIPIENT_FILE": str(recipient_file),
            "PIIGHOST_BACKUP_DIR": str(backup_dir),
            "PIIGHOST_BACKUP_TIMESTAMP": "2026-04-21",
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    archive = backup_dir / "piighost-2026-04-21.tar.age"
    assert archive.exists()
    assert archive.stat().st_size > 0

    restore_dir = tmp_path / "restored"
    restore_dir.mkdir()
    result = subprocess.run(
        ["bash", str(RESTORE), str(archive)],
        env={
            **os.environ,
            "PIIGHOST_DATA_DIR": str(restore_dir),
            "PIIGHOST_AGE_KEY_FILE": str(key_path),
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert (restore_dir / "vault" / "store.db").read_bytes() == b"encrypted-payload"
    assert (restore_dir / "audit" / "log").read_text() == "entry 1\nentry 2\n"
