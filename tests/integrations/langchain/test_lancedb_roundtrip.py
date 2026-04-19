"""Anonymize → embed (local Solon OR cloud Mistral) → LanceDB → query → rehydrate.

Parametrized over the two supported embedding backends. The Mistral branch also
asserts no raw PII is ever sent over the wire (the whole reason anonymizer must
run before the embedder).
"""

import os

import pytest

pytest.importorskip("langchain_core")
pytest.importorskip("lancedb")
pytest.importorskip("langchain_community")

pytestmark = [pytest.mark.asyncio, pytest.mark.slow]

from langchain_community.vectorstores import LanceDB  # noqa: E402
from langchain_core.documents import Document  # noqa: E402

from piighost.integrations.langchain.transformers import (  # noqa: E402
    PIIGhostDocumentAnonymizer,
    PIIGhostQueryAnonymizer,
    PIIGhostRehydrator,
)


def _make_embeddings(backend: str):
    if backend == "local":
        pytest.importorskip("sentence_transformers")
        pytest.importorskip("langchain_huggingface")
        from langchain_huggingface import HuggingFaceEmbeddings

        return HuggingFaceEmbeddings(
            model_name="OrdalieTech/Solon-embeddings-base-0.1",
            encode_kwargs={"normalize_embeddings": True},
            query_encode_kwargs={"prompt": "query: "},
        )
    if backend == "mistral":
        pytest.importorskip("langchain_mistralai")
        if not os.getenv("MISTRAL_API_KEY"):
            pytest.skip("MISTRAL_API_KEY not set")
        from langchain_mistralai import MistralAIEmbeddings

        return MistralAIEmbeddings(model="mistral-embed")
    raise ValueError(f"unknown backend: {backend}")


@pytest.mark.parametrize("backend", ["local", "mistral"])
async def test_anonymize_index_query_rehydrate(backend, pipeline, tmp_path) -> None:
    anonymizer = PIIGhostDocumentAnonymizer(pipeline=pipeline)
    query_anon = PIIGhostQueryAnonymizer(pipeline=pipeline)
    rehydrator = PIIGhostRehydrator()
    embeddings = _make_embeddings(backend)

    raw = [
        Document(page_content="Alice visited Paris", metadata={"source": "a"}),
        Document(page_content="Bob stayed home", metadata={"source": "b"}),
    ]
    anonymized = await anonymizer.atransform_documents(raw)

    # Safety net: raw PII must be absent from page_content before the embedder
    # ever sees it (cloud case) — this is the core ordering invariant.
    for d in anonymized:
        assert "Alice" not in d.page_content
        assert "Paris" not in d.page_content

    db_path = str(tmp_path / "lancedb")
    store = LanceDB.from_documents(
        list(anonymized), embeddings, uri=db_path, table_name="piighost_test"
    )

    qresult = await query_anon.ainvoke("Where did Alice go?")
    assert "Alice" not in qresult["query"]
    hits = store.similarity_search(qresult["query"], k=2)
    assert hits, "retriever should return at least one hit"

    rehydrated = await rehydrator.atransform_documents(hits)
    joined = " ".join(d.page_content for d in rehydrated)
    assert "Alice" in joined
