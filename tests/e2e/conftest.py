"""Gate heavy E2E tests behind their optional extras.

Every E2E file listed below drives ``svc.index_path()`` end-to-end, which
needs ``kreuzberg`` (the ``[index]`` extra) for document extraction.
Without the extra, extraction silently yields no documents and tests
fail with bogus ``assert 0 == N`` errors rather than a clean skip.

We gate collection at the conftest level — so the module-level imports
of heavy optional deps (``haystack``, ``langchain``, …) inside the test
files never run in slim CI environments.
"""
from __future__ import annotations

from importlib.util import find_spec

if find_spec("kreuzberg") is None:
    collect_ignore = [
        "test_haystack_rag_advanced.py",
        "test_haystack_rag_roundtrip.py",
        "test_hacienda_cowork_smoke.py",
        "test_incremental_indexing.py",
        "test_index_query_roundtrip.py",
        "test_langchain_rag_advanced.py",
        "test_langchain_rag_roundtrip.py",
        "test_project_isolation.py",
    ]
