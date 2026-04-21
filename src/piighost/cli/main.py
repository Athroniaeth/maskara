"""piighost CLI entry point (typer app)."""

from __future__ import annotations

import typer

from piighost.cli.commands import anonymize as anonymize_cmd
from piighost.cli.commands import detect as detect_cmd
from piighost.cli.commands import index as index_cmd
from piighost.cli.commands import index_status as index_status_cmd
from piighost.cli.commands import init as init_cmd
from piighost.cli.commands import query as query_cmd
from piighost.cli.commands import rehydrate as rehydrate_cmd
from piighost.cli.commands import rm as rm_cmd
from piighost.cli.commands import serve as serve_cmd
from piighost.cli.commands.daemon import daemon_app
from piighost.cli.commands.projects import app as projects_app
from piighost.cli.commands.vault import vault_app
from piighost.cli.docker_cmd import app as docker_app
from piighost.cli.self_update import app as self_update_app

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="piighost — GDPR-compliant PII anonymization CLI",
)

app.command("init")(init_cmd.run)
app.command("anonymize")(anonymize_cmd.run)
app.command("rehydrate")(rehydrate_cmd.run)
app.command("detect")(detect_cmd.run)
app.command("index")(index_cmd.run)
app.command("query")(query_cmd.run)
app.command("serve")(serve_cmd.run)
app.command("rm")(rm_cmd.run)
app.command("index-status")(index_status_cmd.run)
app.add_typer(vault_app, name="vault")
app.add_typer(daemon_app, name="daemon")
app.add_typer(projects_app, name="projects")
app.add_typer(docker_app, name="docker")
app.add_typer(self_update_app, name="self-update")
