"""End-to-end smoke: init -> daemon -> anonymize -> rehydrate -> stop.

Runs on every OS in the CI matrix.
"""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from piighost.cli.main import app


def test_full_workflow(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("PIIGHOST_DETECTOR", "stub")
    env = {"PIIGHOST_CWD": str(tmp_path), "PIIGHOST_DETECTOR": "stub"}
    runner = CliRunner()

    assert runner.invoke(app, ["init"], env=env).exit_code == 0
    assert runner.invoke(app, ["daemon", "start"], env=env).exit_code == 0
    try:
        a = runner.invoke(app, ["anonymize", "-"], input="Alice in Paris", env=env)
        assert a.exit_code == 0, a.stderr
        anon = json.loads(a.stdout.strip().splitlines()[-1])["anonymized"]
        r = runner.invoke(app, ["rehydrate", "-"], input=anon, env=env)
        assert r.exit_code == 0, r.stderr
        payload = json.loads(r.stdout.strip().splitlines()[-1])
        assert payload["text"] == "Alice in Paris"
    finally:
        runner.invoke(app, ["daemon", "stop"], env=env)
