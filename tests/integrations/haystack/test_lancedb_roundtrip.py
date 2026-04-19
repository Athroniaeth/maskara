"""LanceDB-Haystack roundtrip: verify PyArrow schema survives write/read.

Gated on the ``lancedb_haystack`` extra via ``importorskip``. Marked
``slow`` so it does not run in the default fast test suite.
"""

import pyarrow as pa
import pytest

lancedb_haystack = pytest.importorskip("lancedb_haystack")

from haystack import Document  # noqa: E402

from piighost.integrations.haystack import (  # noqa: E402
    PIIGhostDocumentAnonymizer,
    PIIGhostRehydrator,
    lancedb_meta_fields,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.slow]


async def test_mapping_survives_lancedb_roundtrip(tmp_path, pipeline) -> None:
    store = lancedb_haystack.LanceDBDocumentStore(
        database=str(tmp_path / "lance.db"),
        table_name="test",
        metadata_schema=pa.struct([*lancedb_meta_fields()]),
        embedding_dims=8,
    )

    anonymizer = PIIGhostDocumentAnonymizer(pipeline=pipeline)
    rehydrator = PIIGhostRehydrator()

    doc = Document(content="Patrick habite à Paris.")
    anon_out = await anonymizer.run_async(documents=[doc])
    store.write_documents(anon_out["documents"])

    read_back = store.filter_documents()
    assert len(read_back) == 1
    assert "piighost_mapping" in read_back[0].meta

    rehyd_out = await rehydrator.run_async(documents=read_back)
    assert rehyd_out["documents"][0].content == "Patrick habite à Paris."
