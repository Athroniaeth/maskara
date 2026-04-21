"""MCP surface additions that back the hacienda Cowork plugin."""
from __future__ import annotations

from pathlib import Path

import pytest

from piighost.mcp.server import build_mcp


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
