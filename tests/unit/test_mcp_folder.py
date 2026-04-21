# tests/unit/test_mcp_folder.py
"""Deterministic folder → project-name hasher for hacienda."""
from __future__ import annotations

from pathlib import Path

from piighost.mcp.folder import project_name_for_folder


class TestProjectNameForFolder:
    def test_stable_for_same_path(self) -> None:
        a = project_name_for_folder(Path("/home/user/Dossiers/ACME"))
        b = project_name_for_folder(Path("/home/user/Dossiers/ACME"))
        assert a == b

    def test_different_paths_different_names(self) -> None:
        a = project_name_for_folder(Path("/home/user/Dossiers/ACME"))
        b = project_name_for_folder(Path("/home/user/Dossiers/BETA"))
        assert a != b

    def test_windows_case_insensitive(self) -> None:
        # Windows paths: drive letter case must not matter.
        a = project_name_for_folder(Path(r"C:\Users\Maitre\Dossiers\ACME"))
        b = project_name_for_folder(Path(r"c:\Users\Maitre\Dossiers\ACME"))
        assert a == b

    def test_trailing_separator_ignored(self) -> None:
        a = project_name_for_folder(Path("/home/user/ACME"))
        b = project_name_for_folder(Path("/home/user/ACME/"))
        assert a == b

    def test_format_is_slug_dash_hash8(self) -> None:
        name = project_name_for_folder(Path("/home/user/Dossiers/ACME Inc."))
        # "acme-inc-" slug + 8 hex chars hash
        assert "-" in name
        slug, _, hash_part = name.rpartition("-")
        assert len(hash_part) == 8
        assert all(c in "0123456789abcdef" for c in hash_part)
        assert slug == "acme-inc"

    def test_empty_leaf_falls_back_to_root(self) -> None:
        # Path("/") has empty .name — hasher must still produce a valid name.
        name = project_name_for_folder(Path("/"))
        assert name  # non-empty
        assert name.endswith(tuple("0123456789abcdef"))
