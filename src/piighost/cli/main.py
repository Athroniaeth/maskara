"""piighost CLI entry point (typer app)."""

from __future__ import annotations

import os
from pathlib import Path

import typer

from piighost.cli.commands import anonymize as anonymize_cmd
from piighost.cli.commands import detect as detect_cmd
from piighost.cli.commands import init as init_cmd
from piighost.cli.commands import rehydrate as rehydrate_cmd
from piighost.cli.commands.vault import vault_app

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="piighost — GDPR-compliant PII anonymization CLI",
)

app.command("init")(init_cmd.run)
app.command("anonymize")(anonymize_cmd.run)
app.command("rehydrate")(rehydrate_cmd.run)
app.command("detect")(detect_cmd.run)
app.add_typer(vault_app, name="vault")


def _effective_cwd() -> Path:
    return Path(os.environ.get("PIIGHOST_CWD", Path.cwd()))
