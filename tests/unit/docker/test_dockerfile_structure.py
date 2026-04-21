"""Dockerfile structural invariants — fast, no image build required."""
from __future__ import annotations

from pathlib import Path

import pytest

DOCKERFILE = Path("docker/Dockerfile")


@pytest.fixture(scope="module")
def dockerfile_text() -> str:
    return DOCKERFILE.read_text(encoding="utf-8")


def test_dockerfile_has_slim_target(dockerfile_text: str) -> None:
    assert "AS slim" in dockerfile_text, "slim stage missing"


def test_slim_uses_distroless_nonroot(dockerfile_text: str) -> None:
    assert "gcr.io/distroless/python3-debian12:nonroot" in dockerfile_text


def test_slim_runs_as_uid_10001(dockerfile_text: str) -> None:
    # distroless ships UID 65532 as `nonroot`; we override to 10001 explicitly
    assert "USER 10001" in dockerfile_text, "non-root UID not set to 10001"


def test_dockerfile_pins_base_by_digest(dockerfile_text: str) -> None:
    # Every FROM must carry an @sha256: digest pin for supply-chain integrity
    from_lines = [l for l in dockerfile_text.splitlines() if l.strip().startswith("FROM ")]
    assert from_lines, "no FROM directives found"
    for line in from_lines:
        assert "@sha256:" in line, f"unpinned base image: {line!r}"


def test_dockerfile_no_apt_without_clean(dockerfile_text: str) -> None:
    if "apt-get install" in dockerfile_text:
        assert "rm -rf /var/lib/apt/lists" in dockerfile_text


def test_dockerfile_declares_healthcheck(dockerfile_text: str) -> None:
    assert "HEALTHCHECK" in dockerfile_text
