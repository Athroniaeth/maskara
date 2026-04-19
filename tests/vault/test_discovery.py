from pathlib import Path

import pytest

from piighost.exceptions import VaultNotFound
from piighost.vault.discovery import find_vault_dir


def test_finds_in_cwd(tmp_path: Path) -> None:
    (tmp_path / ".piighost").mkdir()
    assert find_vault_dir(start=tmp_path) == tmp_path / ".piighost"


def test_walks_upward(tmp_path: Path) -> None:
    (tmp_path / ".piighost").mkdir()
    deep = tmp_path / "a" / "b" / "c"
    deep.mkdir(parents=True)
    assert find_vault_dir(start=deep) == tmp_path / ".piighost"


def test_raises_when_absent(tmp_path: Path) -> None:
    with pytest.raises(VaultNotFound):
        find_vault_dir(start=tmp_path)


def test_explicit_override(tmp_path: Path) -> None:
    explicit = tmp_path / "custom" / ".piighost"
    explicit.mkdir(parents=True)
    assert find_vault_dir(start=tmp_path, explicit=explicit) == explicit
