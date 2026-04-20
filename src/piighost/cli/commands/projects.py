"""`piighost projects {list,create,delete}` — project management."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer

from piighost.cli.commands.vault import _load_cfg, _resolve_vault
from piighost.cli.output import ExitCode, emit_error_line, emit_json_line
from piighost.daemon.client import DaemonClient
from piighost.exceptions import VaultNotFound
from piighost.service import PIIGhostService


app = typer.Typer(help="Manage piighost projects (isolated vaults + retrieval).")


@app.command("list")
def list_cmd(
    vault: Path | None = typer.Option(None, "--vault"),
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
        emit_json_line(client.call("list_projects", {}))
        return

    asyncio.run(_list(vault_dir))


async def _list(vault_dir: Path) -> None:
    config = _load_cfg(vault_dir)
    svc = await PIIGhostService.create(vault_dir=vault_dir, config=config)
    try:
        projects = await svc.list_projects()
        emit_json_line(
            [
                {
                    "name": p.name,
                    "description": p.description,
                    "created_at": p.created_at,
                    "last_accessed_at": p.last_accessed_at,
                }
                for p in projects
            ]
        )
    finally:
        await svc.close()


@app.command("create")
def create_cmd(
    name: str = typer.Argument(..., help="Project name"),
    description: str = typer.Option("", "--description"),
    vault: Path | None = typer.Option(None, "--vault"),
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
        emit_json_line(
            client.call("create_project", {"name": name, "description": description})
        )
        return

    asyncio.run(_create(vault_dir, name, description))


async def _create(vault_dir: Path, name: str, description: str) -> None:
    config = _load_cfg(vault_dir)
    svc = await PIIGhostService.create(vault_dir=vault_dir, config=config)
    try:
        info = await svc.create_project(name, description=description)
        emit_json_line(
            {
                "name": info.name,
                "description": info.description,
                "created_at": info.created_at,
            }
        )
    finally:
        await svc.close()


@app.command("delete")
def delete_cmd(
    name: str = typer.Argument(..., help="Project name"),
    force: bool = typer.Option(False, "--force/--no-force"),
    vault: Path | None = typer.Option(None, "--vault"),
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
        emit_json_line(
            client.call("delete_project", {"name": name, "force": force})
        )
        return

    asyncio.run(_delete(vault_dir, name, force))


async def _delete(vault_dir: Path, name: str, force: bool) -> None:
    config = _load_cfg(vault_dir)
    svc = await PIIGhostService.create(vault_dir=vault_dir, config=config)
    try:
        deleted = await svc.delete_project(name, force=force)
        emit_json_line({"deleted": deleted, "name": name})
    finally:
        await svc.close()
