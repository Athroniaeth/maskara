"""`piighost detect` — detection only, no vault mutation."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import typer

from piighost.cli.io_utils import read_input
from piighost.cli.output import ExitCode, emit_error_line, emit_json_line
from piighost.daemon.client import DaemonClient
from piighost.exceptions import VaultNotFound
from piighost.vault.discovery import find_vault_dir


def run(
    target: str = typer.Argument(..., help="File path or '-' for stdin"),
    vault: Path | None = typer.Option(None, "--vault"),
    project: str = typer.Option("default", "--project", help="Project name (defaults to 'default')"),
) -> None:
    try:
        vault_dir = find_vault_dir(
            start=Path(os.environ.get("PIIGHOST_CWD", Path.cwd())),
            explicit=vault,
        )
    except VaultNotFound as exc:
        emit_error_line(
            error="VaultNotFound",
            message=str(exc),
            hint="Run `piighost init` or pass --vault",
            exit_code=ExitCode.USER_ERROR,
        )
        raise typer.Exit(code=int(ExitCode.USER_ERROR))

    doc_id, text = read_input(target)

    client = DaemonClient.from_vault(vault_dir)
    if client is not None:
        detections = client.call("detect", {"text": text, "project": project})
        emit_json_line({"doc_id": doc_id, "detections": detections})
        return

    asyncio.run(_run(vault_dir, doc_id, text, project))


async def _run(vault_dir: Path, doc_id: str, text: str, project: str = "default") -> None:
    from piighost.service import PIIGhostService, ServiceConfig

    cfg_path = vault_dir / "config.toml"
    config = (
        ServiceConfig.from_toml(cfg_path) if cfg_path.exists() else ServiceConfig.default()
    )
    svc = await PIIGhostService.create(vault_dir=vault_dir, config=config)
    try:
        dets = await svc.detect(text, project=project)
        emit_json_line({"doc_id": doc_id, "detections": [d.model_dump() for d in dets]})
    finally:
        await svc.close()
