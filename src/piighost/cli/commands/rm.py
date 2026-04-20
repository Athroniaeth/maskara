"""`piighost rm <path>` — remove a document from the index."""
from __future__ import annotations

import asyncio
from pathlib import Path

import typer

from piighost.cli.commands.vault import _load_cfg, _resolve_vault
from piighost.cli.output import ExitCode, emit_error_line, emit_json_line
from piighost.daemon.client import DaemonClient
from piighost.exceptions import VaultNotFound
from piighost.service import PIIGhostService


def run(
    path: Path = typer.Argument(..., help="File to remove from the index"),
    vault: Path | None = typer.Option(None, "--vault"),
    project: str = typer.Option("default", "--project", help="Project name (defaults to 'default')"),
) -> None:
    try:
        vault_dir = _resolve_vault(vault)
    except VaultNotFound as exc:
        emit_error_line(
            error="VaultNotFound",
            message=type(exc).__name__,
            hint="Run `piighost init`",
            exit_code=ExitCode.USER_ERROR,
        )
        raise typer.Exit(code=int(ExitCode.USER_ERROR))

    client = DaemonClient.from_vault(vault_dir)
    if client is not None:
        result = client.call("remove_doc", {"path": str(path.resolve()), "project": project})
        emit_json_line(result)
        return

    asyncio.run(_remove(vault_dir, path, project))


async def _remove(vault_dir: Path, path: Path, project: str = "default") -> None:
    config = _load_cfg(vault_dir)
    svc = await PIIGhostService.create(vault_dir=vault_dir, config=config)
    try:
        removed = await svc.remove_doc(path.resolve(), project=project)
        emit_json_line({"removed": removed})
    finally:
        await svc.close()
