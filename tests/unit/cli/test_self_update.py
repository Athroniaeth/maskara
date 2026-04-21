"""`piighost self-update` rewrites compose digests after verifying signatures."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from piighost.cli.main import app


COMPOSE_BEFORE = """\
services:
  piighost-mcp:
    image: ghcr.io/jamon8888/hacienda-ghost@sha256:OLDDIGEST
  piighost-daemon:
    image: ghcr.io/jamon8888/hacienda-ghost@sha256:OLDDIGEST
"""


@patch("piighost.cli.self_update._fetch_latest_digest")
@patch("piighost.cli.self_update._verify_cosign_signature")
def test_self_update_rewrites_digests_on_success(
    mock_verify, mock_fetch, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    compose = tmp_path / "docker-compose.yml"
    compose.write_text(COMPOSE_BEFORE)

    mock_fetch.return_value = "sha256:NEWDIGEST"
    mock_verify.return_value = True

    runner = CliRunner()
    result = runner.invoke(app, ["self-update", "--yes"])
    assert result.exit_code == 0, result.stdout
    text = compose.read_text()
    assert "NEWDIGEST" in text
    assert "OLDDIGEST" not in text


@patch("piighost.cli.self_update._fetch_latest_digest")
@patch("piighost.cli.self_update._verify_cosign_signature")
def test_self_update_aborts_on_signature_failure(
    mock_verify, mock_fetch, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    compose = tmp_path / "docker-compose.yml"
    compose.write_text(COMPOSE_BEFORE)

    mock_fetch.return_value = "sha256:NEWDIGEST"
    mock_verify.return_value = False

    runner = CliRunner()
    result = runner.invoke(app, ["self-update", "--yes"])
    assert result.exit_code != 0
    # Compose file must be untouched
    assert compose.read_text() == COMPOSE_BEFORE
