"""KreuzbergLoader → PIIGhostDocumentAnonymizer end-to-end."""

import pytest

pytest.importorskip("langchain_core")
pytest.importorskip("langchain_kreuzberg")

pytestmark = [pytest.mark.asyncio, pytest.mark.slow]

from langchain_kreuzberg import KreuzbergLoader  # noqa: E402

from piighost.integrations.langchain.transformers import (  # noqa: E402
    PIIGhostDocumentAnonymizer,
)


async def test_loader_into_anonymizer(pipeline, tmp_path) -> None:
    sample = tmp_path / "sample.txt"
    sample.write_text("Alice visited Paris in April.", encoding="utf-8")

    loader = KreuzbergLoader(str(sample))
    docs = await loader.aload()
    assert docs and docs[0].page_content.strip()

    anonymizer = PIIGhostDocumentAnonymizer(pipeline=pipeline)
    out = await anonymizer.atransform_documents(docs)

    assert "Alice" not in out[0].page_content
    assert "piighost_mapping" in out[0].metadata
    assert "source" in out[0].metadata
