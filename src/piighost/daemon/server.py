"""Starlette app exposing PIIGhostService over JSON-RPC at /rpc.

Loopback-only. Bearer-token auth via Authorization header.
"""

from __future__ import annotations

import asyncio
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from piighost.service import PIIGhostService
from piighost.service.config import ServiceConfig


def build_app(vault_dir: Path) -> tuple[Starlette, str]:
    token = secrets.token_urlsafe(32)
    cfg_path = vault_dir / "config.toml"
    config = (
        ServiceConfig.from_toml(cfg_path) if cfg_path.exists() else ServiceConfig.default()
    )

    state: dict[str, Any] = {"service": None}
    shutdown_event = asyncio.Event()

    @asynccontextmanager
    async def lifespan(_: Starlette) -> AsyncIterator[None]:
        state["service"] = await PIIGhostService.create(
            vault_dir=vault_dir, config=config
        )
        try:
            yield
        finally:
            svc: PIIGhostService | None = state["service"]
            if svc:
                await svc.close()

    async def health(_: Request) -> JSONResponse:
        return JSONResponse({"ok": True})

    async def rpc(request: Request) -> JSONResponse:
        auth = request.headers.get("authorization", "")
        if not auth.startswith("Bearer ") or auth[7:] != token:
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        body = await request.json()
        method = body.get("method")
        params = body.get("params", {}) or {}
        svc: PIIGhostService = state["service"]
        try:
            result = await _dispatch(svc, method, params)
        except Exception as exc:  # noqa: BLE001
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": body.get("id"),
                    "error": {"code": -32000, "message": type(exc).__name__},
                }
            )
        return JSONResponse(
            {"jsonrpc": "2.0", "id": body.get("id"), "result": result}
        )

    async def shutdown(request: Request) -> JSONResponse:
        auth = request.headers.get("authorization", "")
        if not auth.startswith("Bearer ") or auth[7:] != token:
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        shutdown_event.set()
        return JSONResponse({"ok": True})

    routes = [
        Route("/health", health),
        Route("/rpc", rpc, methods=["POST"]),
        Route("/shutdown", shutdown, methods=["POST"]),
    ]
    app = Starlette(routes=routes, lifespan=lifespan)
    app.state.shutdown_event = shutdown_event
    return app, token


async def _dispatch(
    svc: PIIGhostService, method: str, params: dict[str, Any]
) -> Any:
    if method == "anonymize":
        r = await svc.anonymize(params["text"], doc_id=params.get("doc_id"))
        return r.model_dump()
    if method == "rehydrate":
        r = await svc.rehydrate(params["text"], strict=params.get("strict"))
        return r.model_dump()
    if method == "detect":
        return [d.model_dump() for d in await svc.detect(params["text"])]
    if method == "vault_list":
        r = await svc.vault_list(
            label=params.get("label"),
            limit=params.get("limit", 100),
            reveal=params.get("reveal", False),
        )
        return r.model_dump()
    if method == "vault_show":
        r = await svc.vault_show(params["token"], reveal=params.get("reveal", False))
        return r.model_dump() if r else None
    if method == "vault_stats":
        return (await svc.vault_stats()).model_dump()
    if method == "vault_search":
        entries = await svc.vault_search(
            params["query"], reveal=params.get("reveal", False), limit=params.get("limit", 100)
        )
        return [e.model_dump() for e in entries]
    if method == "index_path":
        report = await svc.index_path(
            Path(params["path"]), recursive=params.get("recursive", True)
        )
        return report.model_dump()
    if method == "query":
        result = await svc.query(params["text"], k=params.get("k", 5))
        return result.model_dump()
    raise ValueError(f"Unknown method: {method}")
