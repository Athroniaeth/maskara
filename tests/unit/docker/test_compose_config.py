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


def _compose_config(*extra_args: str) -> dict:
    """Return the fully-resolved compose config as a dict."""
    result = subprocess.run(
        ["docker", "compose", *extra_args, "config", "--format", "json"],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def test_workstation_profile_brings_up_mcp_and_daemon() -> None:
    cfg = _compose_config("--profile", "workstation")
    services = cfg["services"]
    assert "piighost-mcp" in services
    assert "piighost-daemon" in services
    assert "piighost-backup" in services
    # Caddy is server-only
    assert "caddy" not in services


def test_all_services_run_as_uid_10001() -> None:
    cfg = _compose_config("--profile", "workstation")
    for name, spec in cfg["services"].items():
        assert spec.get("user") == "10001:10001", (
            f"service {name!r} does not run as UID 10001: user={spec.get('user')!r}"
        )


def test_all_services_drop_all_caps() -> None:
    cfg = _compose_config("--profile", "workstation")
    for name, spec in cfg["services"].items():
        cap_drop = spec.get("cap_drop", [])
        assert "ALL" in cap_drop, f"{name!r} does not cap_drop: [ALL]"


def test_all_services_read_only_filesystem() -> None:
    cfg = _compose_config("--profile", "workstation")
    for name, spec in cfg["services"].items():
        assert spec.get("read_only") is True, f"{name!r} read_only != true"


def test_all_services_no_new_privileges() -> None:
    cfg = _compose_config("--profile", "workstation")
    for name, spec in cfg["services"].items():
        sec_opts = spec.get("security_opt", [])
        assert "no-new-privileges:true" in sec_opts, (
            f"{name!r} missing no-new-privileges:true"
        )


def test_mcp_bound_loopback_only_on_workstation() -> None:
    cfg = _compose_config("--profile", "workstation")
    ports = cfg["services"]["piighost-mcp"].get("ports", [])
    for p in ports:
        host_ip = p.get("host_ip") or ""
        assert host_ip in ("127.0.0.1", "::1"), (
            f"workstation MCP must bind loopback only, got host_ip={host_ip!r}"
        )


def test_vault_key_delivered_via_secret_not_env() -> None:
    cfg = _compose_config("--profile", "workstation")
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
