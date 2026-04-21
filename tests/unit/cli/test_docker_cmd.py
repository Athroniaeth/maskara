"""`piighost docker init` generates secrets and .env atomically."""
from __future__ import annotations

import base64
from pathlib import Path

from typer.testing import CliRunner

from piighost.cli.main import app


def test_docker_init_generates_all_secret_files(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "docker" / "secrets").mkdir(parents=True)
    (tmp_path / "docker" / "secrets" / "vault-key.example").write_text("# tpl\n")

    runner = CliRunner()
    result = runner.invoke(app, ["docker", "init", "--yes"])
    assert result.exit_code == 0, result.stdout

    vault_key = (tmp_path / "docker" / "secrets" / "vault-key.txt").read_text().strip()
    # 32 bytes base64url, no padding → 43 chars
    assert len(vault_key) == 43
    base64.urlsafe_b64decode(vault_key + "=")  # round-trip parse

    import os
    if os.name == "posix":
        mode = (tmp_path / "docker" / "secrets" / "vault-key.txt").stat().st_mode & 0o777
        assert mode == 0o600


def test_docker_init_refuses_to_overwrite_existing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "docker" / "secrets").mkdir(parents=True)
    (tmp_path / "docker" / "secrets" / "vault-key.txt").write_text("ALREADY_THERE")

    runner = CliRunner()
    result = runner.invoke(app, ["docker", "init", "--yes"])
    assert result.exit_code != 0
    # Error message may be in stdout or stderr depending on typer version
    combined = (result.stdout + (result.stderr or "")).lower()
    assert "refuse to overwrite" in combined
