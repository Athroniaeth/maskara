import json
from pathlib import Path

from typer.testing import CliRunner

from piighost.cli.main import app


def _setup(tmp_path: Path) -> dict[str, str]:
    env = {"PIIGHOST_CWD": str(tmp_path), "PIIGHOST_DETECTOR": "stub"}
    runner = CliRunner()
    runner.invoke(app, ["init"], env=env)
    runner.invoke(app, ["anonymize", "-"], input="Alice in Paris", env=env)
    return env


def test_vault_list_masks_by_default(tmp_path: Path) -> None:
    env = _setup(tmp_path)
    r = CliRunner().invoke(app, ["vault", "list"], env=env)
    assert r.exit_code == 0
    rows = [json.loads(l) for l in r.stdout.strip().splitlines()]
    assert all(row["original"] is None for row in rows)
    assert any(row["original_masked"] for row in rows)


def test_vault_stats(tmp_path: Path) -> None:
    env = _setup(tmp_path)
    r = CliRunner().invoke(app, ["vault", "stats"], env=env)
    assert r.exit_code == 0
    row = json.loads(r.stdout.strip())
    assert row["total"] == 2
    assert row["by_label"]["PERSON"] == 1
    assert row["by_label"]["LOC"] == 1


def test_vault_show_reveal_writes_audit(tmp_path: Path) -> None:
    env = _setup(tmp_path)
    list_r = CliRunner().invoke(app, ["vault", "list"], env=env)
    token = json.loads(list_r.stdout.strip().splitlines()[0])["token"]
    r = CliRunner().invoke(
        app, ["vault", "show", token, "--reveal"], env=env
    )
    assert r.exit_code == 0
    row = json.loads(r.stdout.strip())
    assert row["original"] is not None
    audit_path = tmp_path / ".piighost" / "audit.log"
    assert "vault_show_reveal" in audit_path.read_text(encoding="utf-8")
