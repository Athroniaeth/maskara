"""End-to-end smoke for the hacienda Cowork plugin's MCP surface.

Script form of the skill prose — every MCP call a hacienda skill makes
is executed here against a real in-process piighost service.

Deviations from the original spec:
- ``mcp.get_resources()`` dict lookup is not the FastMCP 3.x API.  The
  per-folder status resource is a *parameterised template*; it is reached via
  ``await mcp.get_resource_template(uri_pattern)`` → ``template.create_resource``
  → ``resource.read()``.
- The ``query`` tool returns its hits under the key ``"hits"``, not
  ``"results"`` or ``"excerpts"`` (confirmed in
  ``tests/unit/test_mcp_query_filter_rerank.py``).  The excerpt extraction
  has been adapted accordingly; the PII safety-invariant assertion is kept.
- ``PIIGHOST_EMBEDDER=stub`` and ``PIIGHOST_DETECTOR=stub`` must be set so
  the service works without GPU/network resources.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from piighost.mcp.server import build_mcp


@pytest.mark.asyncio
async def test_full_hacienda_flow(tmp_path: Path, monkeypatch) -> None:
    # Use stub backends so the test runs hermetically (no GPU / network needed).
    monkeypatch.setenv("PIIGHOST_EMBEDDER", "stub")
    monkeypatch.setenv("PIIGHOST_DETECTOR", "stub")

    # Set up a fake Cowork folder with a single text document.
    folder = tmp_path / "clients" / "ACME"
    folder.mkdir(parents=True)
    (folder / "note.txt").write_text(
        "Contact: Jean Martin, 01 23 45 67 89. Contract signed 2025-03-12.",
        encoding="utf-8",
    )

    monkeypatch.setenv("HACIENDA_DATA_DIR", str(tmp_path / "hdata"))
    monkeypatch.setenv("CLOAKPIPE_VAULT_KEY", "x" * 48)

    mcp, svc = await build_mcp(vault_dir=tmp_path / "vault")
    try:
        # 1. resolve_project_for_folder
        resolve = await mcp.get_tool("resolve_project_for_folder")
        r = (await resolve.run({"folder": str(folder)})).structured_content
        project = r["project"]
        assert project.startswith("acme-")

        # 2. bootstrap_client_folder
        bootstrap = await mcp.get_tool("bootstrap_client_folder")
        b = (await bootstrap.run({"folder": str(folder)})).structured_content
        assert b["project"] == project

        # 3. index_path
        index = await mcp.get_tool("index_path")
        await index.run({
            "path": str(folder),
            "recursive": True,
            "force": False,
            "project": project,
        })

        # 4. per-folder status resource
        # FastMCP 3.x: parameterised resources are reached via
        # get_resource_template() → create_resource() → read(), not via a
        # get_resources() dict keyed on the URI pattern.
        b64 = base64.urlsafe_b64encode(str(folder).encode()).decode().rstrip("=")
        template = await mcp.get_resource_template(
            "piighost://folders/{b64_path}/status"
        )
        uri = f"piighost://folders/{b64}/status"
        resource = await template.create_resource(uri=uri, params={"b64_path": b64})
        status_payload = json.loads(await resource.read())
        assert status_payload["project"] == project
        assert status_payload["state"] in {"ready", "empty"}

        # 5. query
        # The query tool returns hits under the key "hits" (not "results" /
        # "excerpts" as mentioned in the spec).  We accept all three for
        # forward-compatibility but in practice expect "hits".
        query = await mcp.get_tool("query")
        q_result = await query.run({
            "text": "When was the contract signed?",
            "k": 5,
            "project": project,
            "rerank": False,
        })
        q = q_result.structured_content
        # Unwrap optional FastMCP "result" envelope.
        if isinstance(q, dict) and "result" in q and len(q) == 1:
            q = q["result"]
        excerpts = q.get("hits") or q.get("results") or q.get("excerpts") or []
        assert excerpts, "expected at least one hit for the indexed note"

        # 6. audit round-trip
        append = await mcp.get_tool("session_audit_append")
        await append.run({
            "session_id": "e2e-1",
            "event": "query",
            "payload": {"n_excerpts": len(excerpts), "project": project},
        })
        read = await mcp.get_tool("session_audit_read")
        events = (await read.run({"session_id": "e2e-1"})).structured_content
        if isinstance(events, dict) and "result" in events:
            events = events["result"]
        assert len(events) == 1
        assert events[0]["event"] == "query"
        # Safety invariant: audit payload must not contain raw PII
        assert "Jean Martin" not in json.dumps(events[0])
    finally:
        await svc.close()
