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


@pytest.mark.asyncio
class TestFolderStatusResource:
    async def test_per_folder_status_uses_project_hash(self, tmp_path: Path) -> None:
        import base64
        import json
        config = ServiceConfig(detector=DetectorSection(backend="regex_only"))
        mcp, svc = await build_mcp(vault_dir=tmp_path / "vault", config=config)
        try:
            folder = str(tmp_path / "clients" / "ACME")
            b64 = base64.urlsafe_b64encode(folder.encode()).decode().rstrip("=")
            # FastMCP parameterised resources: get_resource_template is async.
            template = await mcp.get_resource_template("piighost://folders/{b64_path}/status")
            uri = f"piighost://folders/{b64}/status"
            resource = await template.create_resource(uri=uri, params={"b64_path": b64})
            assert resource is not None
            payload = await resource.read()
            data = json.loads(payload)
            assert data["folder"] == folder
            assert data["project"].startswith("acme-")
            assert data["state"] in {"ready", "indexing", "error", "empty"}
        finally:
            await svc.close()


@pytest.mark.asyncio
class TestSessionAuditTools:
    async def test_append_then_read(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("HACIENDA_DATA_DIR", str(tmp_path))
        mcp, svc = await build_mcp(vault_dir=tmp_path / "vault")
        try:
            append = await mcp.get_tool("session_audit_append")
            read = await mcp.get_tool("session_audit_read")
            await append.run({
                "session_id": "s1",
                "event": "anonymize",
                "payload": {"n": 3},
            })
            await append.run({
                "session_id": "s1",
                "event": "rehydrate",
                "payload": {"n": 3},
            })
            result = await read.run({"session_id": "s1"})
            events = result.structured_content
            # FastMCP may wrap list returns under a "result" key — handle both.
            if isinstance(events, dict) and "result" in events:
                events = events["result"]
            assert len(events) == 2
            assert events[0]["event"] == "anonymize"
            assert events[1]["event"] == "rehydrate"
        finally:
            await svc.close()
