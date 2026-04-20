import asyncio
import importlib.util

import pytest


@pytest.fixture()
def built_mcp(tmp_path, monkeypatch):
    monkeypatch.setenv("PIIGHOST_EMBEDDER", "stub")
    monkeypatch.setenv("PIIGHOST_DETECTOR", "stub")
    real_find_spec = importlib.util.find_spec

    def fake(name, *args, **kwargs):
        if name == "sentence_transformers":
            return object()
        return real_find_spec(name, *args, **kwargs)

    monkeypatch.setattr("importlib.util.find_spec", fake)

    from piighost.mcp.server import build_mcp
    mcp, svc = asyncio.run(build_mcp(tmp_path / "vault"))
    yield mcp, svc
    asyncio.run(svc.close())


def test_query_tool_accepts_filter_prefix(built_mcp, tmp_path):
    mcp, svc = built_mcp
    doc = tmp_path / "doc.txt"
    doc.write_text("Alice works here")
    asyncio.run(svc.index_path(doc, project="p"))

    tools = asyncio.run(mcp.get_tools())
    result = asyncio.run(
        tools["query"].run(
            {"text": "Alice", "project": "p", "k": 3, "filter_prefix": str(tmp_path)}
        )
    )
    if hasattr(result, "structured_content") and result.structured_content:
        payload = result.structured_content.get("result", result.structured_content)
    else:
        payload = result
    assert "hits" in payload


def test_query_tool_accepts_rerank_param(built_mcp, tmp_path):
    mcp, svc = built_mcp
    doc = tmp_path / "doc.txt"
    doc.write_text("Alice here")
    asyncio.run(svc.index_path(doc, project="p"))

    tools = asyncio.run(mcp.get_tools())
    result = asyncio.run(
        tools["query"].run({"text": "Alice", "project": "p", "k": 3, "rerank": False})
    )
    if hasattr(result, "structured_content") and result.structured_content:
        payload = result.structured_content.get("result", result.structured_content)
    else:
        payload = result
    assert "hits" in payload
