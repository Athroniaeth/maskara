"""`piighost index <path>` — index a file or directory."""
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
    path: Path = typer.Argument(..., help="File or directory to index"),
    vault: Path | None = typer.Option(None, "--vault"),
    recursive: bool = typer.Option(True, "--recursive/--no-recursive"),
    force: bool = typer.Option(False, "--force/--no-force", help="Re-index even if unchanged"),
    project: str = typer.Option("", "--project", help="Project name (empty = derive from path)"),
) -> None:
    try:
        vault_dir = _resolve_vault(vault)
    except VaultNotFound as exc:
        emit_error_line(
            error="VaultNotFound",
            message=str(exc),
            hint="Run `piighost init`",
            exit_code=ExitCode.USER_ERROR,
        )
        raise typer.Exit(code=int(ExitCode.USER_ERROR))

    client = DaemonClient.from_vault(vault_dir)
    if client is not None:
        result = client.call("index_path", {"path": str(path.resolve()), "recursive": recursive, "force": force, "project": project})
        emit_json_line(result)
        return

    asyncio.run(_index(vault_dir, path, recursive, force, project))


async def _index(vault_dir: Path, path: Path, recursive: bool, force: bool, project: str = "") -> None:
    config = _load_cfg(vault_dir)
    svc = await PIIGhostService.create(vault_dir=vault_dir, config=config)
    try:
        report = await svc.index_path(path.resolve(), recursive=recursive, force=force, project=project)
        emit_json_line(report.model_dump())
    finally:
        await svc.close()
