"""Exit-code coverage: verify CLI returns the documented codes.

- Missing vault on anonymize → exit 2 (USER_ERROR) with "VaultNotFound" in stderr.
- Unknown rehydrate token in strict mode → exit 5 (PII_SAFETY_VIOLATION)
  with "PIISafetyViolation" in stderr.
"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from piighost.cli.main import app
from piighost.cli.output import ExitCode


def test_missing_vault_yields_exit_2(tmp_path: Path) -> None:
    env = {"PIIGHOST_CWD": str(tmp_path)}
    r = CliRunner().invoke(app, ["anonymize", "-"], input="x", env=env)
    assert r.exit_code == int(ExitCode.USER_ERROR)
    assert "VaultNotFound" in r.stderr


def test_unknown_token_strict_yields_exit_5(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("PIIGHOST_DETECTOR", "stub")
    env = {"PIIGHOST_CWD": str(tmp_path), "PIIGHOST_DETECTOR": "stub"}
    runner = CliRunner()
    runner.invoke(app, ["init"], env=env)
    r = runner.invoke(
        app, ["rehydrate", "-"], input="see <PERSON:deadbeef>", env=env
    )
    assert r.exit_code == int(ExitCode.PII_SAFETY_VIOLATION)
    assert "PIISafetyViolation" in r.stderr
