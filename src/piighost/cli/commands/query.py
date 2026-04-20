"""`piighost query <text>` — hybrid BM25+vector search."""
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
    text: str = typer.Argument(..., help="Query text"),
    vault: Path | None = typer.Option(None, "--vault"),
    k: int = typer.Option(5, "--k", "-k"),
) -> None:
    try:
        vault_dir = _resolve_vault(vault)
    except VaultNotFound as exc:
        emit_error_line("VaultNotFound", str(exc), "Run `piighost init`", ExitCode.USER_ERROR)
        raise typer.Exit(code=int(ExitCode.USER_ERROR))

    client = DaemonClient.from_vault(vault_dir)
    if client is not None:
        result = client.call("query", {"text": text, "k": k})
        emit_json_line(result)
        return

    asyncio.run(_query(vault_dir, text, k))


async def _query(vault_dir: Path, text: str, k: int) -> None:
    config = _load_cfg(vault_dir)
    svc = await PIIGhostService.create(vault_dir=vault_dir, config=config)
    try:
        result = await svc.query(text, k=k)
        emit_json_line(result.model_dump())
    finally:
        await svc.close()
