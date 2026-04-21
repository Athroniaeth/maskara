"""MCP surface additions that back the hacienda Cowork plugin."""
from __future__ import annotations

from pathlib import Path

import pytest

from piighost.mcp.server import build_mcp
from piighost.service.config import ServiceConfig, DetectorSection


@pytest.mark.asyncio
class TestResolveProjectForFolder:
    async def test_returns_project_name_and_folder(self, tmp_path: Path) -> None:
        mcp, svc = await build_mcp(vault_dir=tmp_path / "vault")
        try:
            tool = await mcp.get_tool("resolve_project_for_folder")
            result = await tool.run({"folder": "/home/user/Dossiers/ACME"})
            # FastMCP wraps the return in a Pydantic model; unwrap to dict.
            data = result.structured_content
            assert data["folder"] == "/home/user/Dossiers/ACME"
            assert data["project"].startswith("acme-")
            assert len(data["project"].rsplit("-", 1)[1]) == 8
        finally:
            await svc.close()

    async def test_same_folder_same_project(self, tmp_path: Path) -> None:
        mcp, svc = await build_mcp(vault_dir=tmp_path / "vault")
        try:
            tool = await mcp.get_tool("resolve_project_for_folder")
            a = await tool.run({"folder": "/home/user/ACME"})
            b = await tool.run({"folder": "/home/user/ACME"})
            assert a.structured_content["project"] == b.structured_content["project"]
        finally:
            await svc.close()


@pytest.mark.asyncio
class TestIndexStatusResource:
    async def test_returns_json_with_expected_keys(self, tmp_path: Path) -> None:
        import json
        config = ServiceConfig(detector=DetectorSection(backend="regex_only"))
        mcp, svc = await build_mcp(vault_dir=tmp_path / "vault", config=config)
        try:
            status = await mcp.get_resource("piighost://index/status")
            assert status is not None
            payload = await status.read()
            data = json.loads(payload)
            assert set(data.keys()) >= {
                "state", "total_docs", "total_chunks", "last_update", "errors"
            }
            assert data["state"] in {"ready", "indexing", "error", "empty"}
            assert isinstance(data["total_docs"], int)
            assert isinstance(data["errors"], list)
        finally:
            await svc.close()
