"""`piighost serve` — run the FastMCP server."""
from __future__ import annotations

from pathlib import Path

import typer

from piighost.cli.commands.vault import _resolve_vault
from piighost.cli.output import ExitCode, emit_error_line
from piighost.exceptions import VaultNotFound


def run(
    vault: Path | None = typer.Option(None, "--vault"),
    transport: str = typer.Option("stdio", "--transport", "-t", help="stdio | sse (mcp transport)"),
) -> None:
    try:
        vault_dir = _resolve_vault(vault)
    except VaultNotFound as exc:
        emit_error_line("VaultNotFound", str(exc), "Run `piighost init`", ExitCode.USER_ERROR)
        raise typer.Exit(code=int(ExitCode.USER_ERROR))

    from piighost.mcp.server import run_mcp
    run_mcp(vault_dir, transport=transport)
