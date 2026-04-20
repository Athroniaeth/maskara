import asyncio
import importlib.util
import pytest


def test_vault_list_uses_service_masking(tmp_path, monkeypatch):
    """vault_list must use service._to_entry_model for correct masking, not inline logic."""
    monkeypatch.setenv("PIIGHOST_EMBEDDER", "stub")
    monkeypatch.setenv("PIIGHOST_DETECTOR", "stub")
    from piighost.mcp.server import build_mcp
    mcp, svc = asyncio.run(build_mcp(tmp_path / "vault"))
    asyncio.run(svc.anonymize("Alice Smith"))
    page = asyncio.run(svc.vault_list(limit=10, reveal=False))
    for entry in page.entries:
        assert entry.original is None  # reveal=False means no raw PII
        assert entry.original_masked is not None  # masked version present
    asyncio.run(svc.close())


def test_build_mcp_returns_fastmcp_and_service(tmp_path, monkeypatch):
    monkeypatch.setenv("PIIGHOST_EMBEDDER", "stub")
    monkeypatch.setenv("PIIGHOST_DETECTOR", "stub")
    from piighost.mcp.server import build_mcp
    mcp, svc = asyncio.run(build_mcp(tmp_path / "vault"))
    assert mcp is not None
    assert svc is not None
    asyncio.run(svc.close())


def test_mcp_has_expected_tools(tmp_path, monkeypatch):
    monkeypatch.setenv("PIIGHOST_EMBEDDER", "stub")
    monkeypatch.setenv("PIIGHOST_DETECTOR", "stub")

    real_find_spec = importlib.util.find_spec

    def fake_find_spec(name, *args, **kwargs):
        if name == "sentence_transformers":
            return object()
        return real_find_spec(name, *args, **kwargs)

    monkeypatch.setattr("importlib.util.find_spec", fake_find_spec)

    from piighost.mcp.server import build_mcp
    mcp, svc = asyncio.run(build_mcp(tmp_path / "vault"))
    # get_tools() is async and returns dict[name, Tool]
    tools = asyncio.run(mcp.get_tools())
    tool_names = set(tools.keys())
    expected = {
        "anonymize_text", "rehydrate_text", "index_path",
        "query", "vault_search", "vault_list", "vault_get",
        "daemon_status", "daemon_stop", "vault_stats",
    }
    assert expected.issubset(tool_names)
    asyncio.run(svc.close())
