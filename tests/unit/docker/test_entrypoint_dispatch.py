"""entrypoint.sh dispatches correctly to each role."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ENTRYPOINT = Path("docker/entrypoint.sh").resolve()

# Resolve bash once so _run can use the absolute path regardless of the
# stripped PATH we pass to the subprocess.  On Linux/CI this is /usr/bin/bash;
# on Git-for-Windows it is e.g. C:\Program Files\Git\usr\bin\bash.EXE.
_BASH = shutil.which("bash") or "bash"

# On Windows the subprocess PATH must include the directory that contains bash
# so that bash itself can find its own builtins and bundled utilities.
_BASE_PATH = "/usr/bin:/bin"
if sys.platform == "win32" and _BASH != "bash":
    import os
    _BASE_PATH = str(Path(_BASH).parent) + os.pathsep + _BASE_PATH


def _run(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [_BASH, str(ENTRYPOINT), *args],
        capture_output=True,
        text=True,
        env={"PATH": _BASE_PATH, "PIIGHOST_DRY_RUN": "1", **(env or {})},
        timeout=10,
    )


def test_entrypoint_exists_and_is_executable() -> None:
    assert ENTRYPOINT.exists()
    content = ENTRYPOINT.read_text(encoding="utf-8")
    assert content.startswith("#!/"), "missing shebang"


def test_entrypoint_rejects_unknown_role() -> None:
    result = _run("bogus")
    assert result.returncode != 0
    assert "unknown role" in (result.stderr + result.stdout).lower()


@pytest.mark.parametrize("role", ["mcp", "daemon", "backup", "notify", "cli"])
def test_entrypoint_accepts_known_role(role: str) -> None:
    result = _run(role)
    assert result.returncode == 0, f"dispatch failed for {role}: {result.stderr}"
    assert role in result.stdout.lower()
