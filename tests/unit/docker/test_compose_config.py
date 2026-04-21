"""`docker compose config` output is well-formed and carries the expected hardening."""
from __future__ import annotations

import json
import shutil
import subprocess

import pytest


def _compose_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        r = subprocess.run(
            ["docker", "compose", "version"],
            capture_output=True, text=True, timeout=5,
        )
        return r.returncode == 0
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _compose_available(),
    reason="docker compose CLI not available in this environment",
)


def _compose_config(*extra_args: str, files: list[str] | None = None) -> dict:
    """Return the fully-resolved compose config as a dict."""
    file_args: list[str] = []
    for f in files or ["docker-compose.yml"]:
        file_args.extend(["-f", f])
    result = subprocess.run(
        ["docker", "compose", *file_args, *extra_args, "config", "--format", "json"],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


_WORKSTATION_FILES = ["docker-compose.yml", "docker-compose.workstation-ports.yml"]
_SERVER_FILES = ["docker-compose.yml"]


def test_workstation_profile_brings_up_mcp_and_daemon() -> None:
    cfg = _compose_config("--profile", "workstation", files=_WORKSTATION_FILES)
    services = cfg["services"]
    assert "piighost-mcp" in services
    assert "piighost-daemon" in services
    assert "piighost-backup" in services
    # Caddy is server-only
    assert "caddy" not in services


def test_all_services_run_as_uid_10001() -> None:
    cfg = _compose_config("--profile", "workstation", files=_WORKSTATION_FILES)
    for name, spec in cfg["services"].items():
        assert spec.get("user") == "10001:10001", (
            f"service {name!r} does not run as UID 10001: user={spec.get('user')!r}"
        )


def test_all_services_drop_all_caps() -> None:
    cfg = _compose_config("--profile", "workstation", files=_WORKSTATION_FILES)
    for name, spec in cfg["services"].items():
        cap_drop = spec.get("cap_drop", [])
        assert "ALL" in cap_drop, f"{name!r} does not cap_drop: [ALL]"


def test_all_services_read_only_filesystem() -> None:
    cfg = _compose_config("--profile", "workstation", files=_WORKSTATION_FILES)
    for name, spec in cfg["services"].items():
        assert spec.get("read_only") is True, f"{name!r} read_only != true"


def test_all_services_no_new_privileges() -> None:
    cfg = _compose_config("--profile", "workstation", files=_WORKSTATION_FILES)
    for name, spec in cfg["services"].items():
        sec_opts = spec.get("security_opt", [])
        assert "no-new-privileges:true" in sec_opts, (
            f"{name!r} missing no-new-privileges:true"
        )


def test_mcp_bound_loopback_only_on_workstation() -> None:
    cfg = _compose_config("--profile", "workstation", files=_WORKSTATION_FILES)
    ports = cfg["services"]["piighost-mcp"].get("ports", [])
    for p in ports:
        host_ip = p.get("host_ip") or ""
        assert host_ip in ("127.0.0.1", "::1"), (
            f"workstation MCP must bind loopback only, got host_ip={host_ip!r}"
        )


def test_vault_key_delivered_via_secret_not_env() -> None:
    cfg = _compose_config("--profile", "workstation", files=_WORKSTATION_FILES)
    mcp = cfg["services"]["piighost-mcp"]
    env = mcp.get("environment", {}) or {}
    if isinstance(env, list):
        env = dict(kv.split("=", 1) for kv in env if "=" in kv)
    assert "PIIGHOST_VAULT_KEY" not in env, (
        "vault key must be delivered via Docker secret, not env var"
    )
    secrets = mcp.get("secrets", [])
    secret_names = [
        s.get("source") if isinstance(s, dict) else s for s in secrets
    ]
    assert "piighost_vault_key" in secret_names


# ---------------------------------------------------------------------------
# Server-profile tests
# ---------------------------------------------------------------------------


def test_server_profile_brings_up_caddy() -> None:
    cfg = _compose_config("--profile", "server", files=_SERVER_FILES)
    assert "caddy" in cfg["services"]


def test_server_profile_caddy_owns_public_ports() -> None:
    cfg = _compose_config("--profile", "server", files=_SERVER_FILES)
    caddy = cfg["services"]["caddy"]
    published_ports = [int(p["published"]) for p in caddy.get("ports", []) if p.get("published")]
    assert 443 in published_ports, "caddy must publish 443"
    # MCP should NOT publish any port directly on server profile
    mcp = cfg["services"]["piighost-mcp"]
    assert not mcp.get("ports"), "MCP must not publish ports in server profile"


def test_server_profile_mtls_mode_configurable() -> None:
    cfg = _compose_config("--profile", "server", files=_SERVER_FILES)
    caddy = cfg["services"]["caddy"]
    env = caddy.get("environment", {}) or {}
    if isinstance(env, list):
        env = dict(kv.split("=", 1) for kv in env if "=" in kv)
    # PIIGHOST_AUTH should be configurable (bearer | mtls)
    assert "PIIGHOST_AUTH" in env


def test_embedder_overlay_adds_sentence_transformers_service() -> None:
    cfg = _compose_config(
        "--profile", "workstation",
        files=["docker-compose.yml", "docker-compose.embedder.yml"],
    )
    assert "piighost-embedder" in cfg["services"]
    embedder = cfg["services"]["piighost-embedder"]
    # Must be on internal network — no egress
    nets = embedder.get("networks", {})
    net_names = list(nets) if isinstance(nets, dict) else nets
    assert "piighost-internal" in net_names


def test_llm_overlay_adds_ollama_on_isolated_network() -> None:
    cfg = _compose_config(
        "--profile", "workstation",
        files=["docker-compose.yml", "docker-compose.llm.yml"],
    )
    assert "ollama" in cfg["services"]
    assert "piighost-llm" in cfg["networks"]
