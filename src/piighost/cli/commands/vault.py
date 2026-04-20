"""`piighost vault list/show/stats`."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import typer

from piighost.cli.output import ExitCode, emit_error_line, emit_json_line
from piighost.daemon.client import DaemonClient
from piighost.exceptions import VaultNotFound
from piighost.service import PIIGhostService
from piighost.service.config import ServiceConfig
from piighost.vault.discovery import find_vault_dir

vault_app = typer.Typer(no_args_is_help=True)


def _resolve_vault(explicit: Path | None) -> Path:
    return find_vault_dir(
        start=Path(os.environ.get("PIIGHOST_CWD", Path.cwd())),
        explicit=explicit,
    )


def _load_cfg(vault_dir: Path) -> ServiceConfig:
    cfg = vault_dir / "config.toml"
    return ServiceConfig.from_toml(cfg) if cfg.exists() else ServiceConfig.default()


@vault_app.command("list")
def list_cmd(
    label: str | None = typer.Option(None, "--label"),
    limit: int = typer.Option(100, "--limit"),
    reveal: bool = typer.Option(False, "--reveal"),
    vault: Path | None = typer.Option(None, "--vault"),
    project: str = typer.Option("default", "--project", help="Project name (defaults to 'default')"),
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
        page = client.call(
            "vault_list",
            {"label": label, "limit": limit, "reveal": reveal, "project": project},
        )
        for entry in page.get("entries", []):
            emit_json_line(entry)
        return

    asyncio.run(_list(vault_dir, label, limit, reveal, project))


async def _list(vault_dir: Path, label: str | None, limit: int, reveal: bool, project: str = "default") -> None:
    config = _load_cfg(vault_dir)
    svc = await PIIGhostService.create(vault_dir=vault_dir, config=config)
    try:
        page = await svc.vault_list(label=label, limit=limit, reveal=reveal, project=project)
        for entry in page.entries:
            emit_json_line(entry.model_dump())
    finally:
        await svc.close()


@vault_app.command("show")
def show_cmd(
    token: str,
    reveal: bool = typer.Option(False, "--reveal"),
    vault: Path | None = typer.Option(None, "--vault"),
    project: str = typer.Option("default", "--project", help="Project name (defaults to 'default')"),
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
        entry = client.call(
            "vault_show", {"token": token, "reveal": reveal, "project": project}
        )
        if entry is None:
            emit_error_line(
                error="TokenNotFound",
                message=f"no entry for {token}",
                hint=None,
                exit_code=ExitCode.USER_ERROR,
            )
            raise typer.Exit(code=int(ExitCode.USER_ERROR))
        emit_json_line(entry)
        return

    asyncio.run(_show(vault_dir, token, reveal, project))


async def _show(vault_dir: Path, token: str, reveal: bool, project: str = "default") -> None:
    config = _load_cfg(vault_dir)
    svc = await PIIGhostService.create(vault_dir=vault_dir, config=config)
    try:
        entry = await svc.vault_show(token, reveal=reveal, project=project)
        if entry is None:
            emit_error_line(
                error="TokenNotFound",
                message=f"no entry for {token}",
                hint=None,
                exit_code=ExitCode.USER_ERROR,
            )
            raise typer.Exit(code=int(ExitCode.USER_ERROR))
        emit_json_line(entry.model_dump())
    finally:
        await svc.close()


@vault_app.command("stats")
def stats_cmd(
    vault: Path | None = typer.Option(None, "--vault"),
    project: str = typer.Option("default", "--project", help="Project name (defaults to 'default')"),
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
        stats = client.call("vault_stats", {"project": project})
        emit_json_line(stats)
        return

    asyncio.run(_stats(vault_dir, project))


async def _stats(vault_dir: Path, project: str = "default") -> None:
    config = _load_cfg(vault_dir)
    svc = await PIIGhostService.create(vault_dir=vault_dir, config=config)
    try:
        s = await svc.vault_stats(project=project)
        emit_json_line(s.model_dump())
    finally:
        await svc.close()


@vault_app.command("search")
def search_cmd(
    query: str = typer.Argument(..., help="Search term"),
    reveal: bool = typer.Option(False, "--reveal"),
    limit: int = typer.Option(100, "--limit"),
    vault: Path | None = typer.Option(None, "--vault"),
    project: str = typer.Option("default", "--project", help="Project name (defaults to 'default')"),
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
        results = client.call("vault_search", {"query": query, "reveal": reveal, "limit": limit, "project": project})
        for entry in results:
            emit_json_line(entry)
        return

    asyncio.run(_search(vault_dir, query, reveal, limit, project))


async def _search(vault_dir: Path, query: str, reveal: bool, limit: int, project: str = "default") -> None:
    config = _load_cfg(vault_dir)
    svc = await PIIGhostService.create(vault_dir=vault_dir, config=config)
    try:
        entries = await svc.vault_search(query, reveal=reveal, limit=limit, project=project)
        for e in entries:
            emit_json_line(e.model_dump())
    finally:
        await svc.close()
