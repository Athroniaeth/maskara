"""End-to-end smoke: compose up → call MCP → anonymize → compose down.

Requires a running `docker compose --profile workstation up -d` stack.
CI manages the lifecycle; locally, run:

    docker compose --profile workstation up -d --wait
    pytest tests/e2e/test_docker_smoke.py -v
"""
from __future__ import annotations

import os
import time

import httpx
import pytest

MCP_URL = os.environ.get("PIIGHOST_MCP_URL", "http://127.0.0.1:8765")


@pytest.fixture(scope="module")
def client():
    # Wait up to 30s for the stack to become ready
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            r = httpx.get(f"{MCP_URL}/healthz", timeout=2)
            if r.status_code == 200:
                break
        except httpx.HTTPError:
            pass
        time.sleep(1)
    else:
        pytest.fail(f"MCP at {MCP_URL} never became ready")
    with httpx.Client(base_url=MCP_URL, timeout=10) as c:
        yield c


def test_mcp_list_tools_includes_anonymize(client: httpx.Client) -> None:
    r = client.post("/mcp/tools/list", json={})
    r.raise_for_status()
    names = {t["name"] for t in r.json().get("tools", [])}
    assert "anonymize_text" in names


def test_anonymize_text_strips_pii(client: httpx.Client) -> None:
    r = client.post(
        "/mcp/tools/call",
        json={
            "name": "anonymize_text",
            "arguments": {"text": "Alice habite à Paris."},
        },
    )
    r.raise_for_status()
    out = r.json()
    anonymized = out["content"][0]["text"]
    assert "Alice" not in anonymized
