# piighost Sprint 6a — LangChain & Haystack RAG Wrappers Design

**Date:** 2026-04-20
**Scope:** Ship convenience wrapper classes (`PIIGhostRAG` for LangChain, `build_piighost_rag` for Haystack) that bundle the full "load → anonymize → embed → vector-store → retrieve → rehydrate" flow so users can get a working PII-safe RAG in ~5 lines of code. Also fix the one bitrot test (`test_hybrid_retrieval.py`) that blocks the LangChain suite from running cleanly.

---

## Goals

1. Fix `tests/integrations/langchain/test_hybrid_retrieval.py` import (`langchain.retrievers → langchain_community.retrievers`). Full LangChain test suite runs clean with real deps installed.
2. New `PIIGhostRAG` class for LangChain — wraps `PIIGhostService`, exposes convenience `.ingest()` / `.query()` methods plus composable `.anonymizer` / `.retriever` / `.rehydrator` runnables.
3. New Haystack `build_piighost_rag(svc, project, llm_generator)` factory returning a pre-wired `Pipeline`, plus a `PIIGhostRetriever` Haystack component.
4. Both wrappers preserve piighost's PII-zero-leak invariant: the LLM receives only anonymized text + opaque tokens, never raw PII.
5. End-to-end roundtrip tests (one per integration) that prove ingestion → query → rehydrated answer works with fake LLMs, and that the LLM input never contains raw PII.

## Non-goals

- Cross-encoder reranking (Sprint 6b).
- Metadata filters (Sprint 6b).
- Streaming responses (Sprint 6b).
- Answer caching (Sprint 6b).
- Post-hoc PII scan of LLM output to catch hallucinated PII (Sprint 6b — rejected for 6a because it needs its own design work).
- Bundling specific LLMs or prompts — user provides the LLM.
- Supporting retrievers other than the piighost-native `svc.query()` in the convenience path. (Users who want a LangChain `EnsembleRetriever` can compose `rag.retriever` themselves.)

---

## 1. Architecture

```
src/piighost/integrations/
├── langchain/
│   ├── rag.py                      [NEW] PIIGhostRAG class + LCEL runnables
│   ├── __init__.py                 [MODIFY] re-export PIIGhostRAG
│   └── (existing transformers.py, middleware.py unchanged)
└── haystack/
    ├── rag.py                      [NEW] build_piighost_rag + PIIGhostRetriever
    ├── __init__.py                 [MODIFY] re-export new symbols
    └── (existing components unchanged)
```

Both wrappers delegate all vault/retrieval operations to `PIIGhostService` (from Sprint 5's multiplexer). The wrappers own no state of their own beyond a reference to the service and a `project` string.

## 2. LangChain wrapper — `PIIGhostRAG`

### 2.1 Public API

```python
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from piighost.service.core import PIIGhostService
from piighost.service.models import IndexReport

if TYPE_CHECKING:
    from langchain_core.runnables import Runnable
    from langchain_core.retrievers import BaseRetriever
    from langchain_core.language_models import BaseLanguageModel


class PIIGhostRAG:
    """End-to-end PII-safe RAG chain backed by :class:`PIIGhostService`.

    One instance per project. Compose ``.anonymizer``, ``.retriever``,
    ``.rehydrator`` into custom chains, or call ``.as_chain(llm)`` for the
    standard pipeline.
    """

    def __init__(self, svc: PIIGhostService, *, project: str = "default") -> None:
        self._svc = svc
        self._project = project

    async def ingest(self, path: Path, *, recursive: bool = True, force: bool = False) -> IndexReport:
        """Index a file or directory into the project's vault + chunk store."""
        return await self._svc.index_path(path, recursive=recursive, force=force, project=self._project)

    async def query(self, text: str, *, k: int = 5, llm: "BaseLanguageModel | None" = None) -> str:
        """Full flow: anonymize → retrieve → LLM answer → rehydrate.

        If ``llm`` is None, returns the raw rehydrated context string
        (useful for tests and debugging; no LLM required).
        """
        ...  # see section 2.2

    @property
    def anonymizer(self) -> "Runnable[str, dict]":
        """Runnable mapping str → {'anonymized': str, 'entities': list[EntityRef]}."""
        ...

    @property
    def retriever(self) -> "BaseRetriever":
        """Langchain BaseRetriever wrapping svc.query() with project scoping."""
        ...

    @property
    def rehydrator(self) -> "Runnable[str, str]":
        """Runnable mapping anonymized text → rehydrated text for this project."""
        ...

    def as_chain(
        self,
        llm: "BaseLanguageModel",
        *,
        prompt: "Any | None" = None,
    ) -> "Runnable[str, str]":
        """Compose anonymize → retrieve → prompt → LLM → rehydrate as one LCEL runnable.

        ``prompt`` is an optional custom ``ChatPromptTemplate`` override. When
        None, the built-in PII-preserving template is used.
        """
        ...
```

### 2.2 `PIIGhostRAG.query` implementation

```python
async def query(self, text: str, *, k: int = 5, llm: "BaseLanguageModel | None" = None) -> str:
    anon = await self._svc.anonymize(text, project=self._project)
    result = await self._svc.query(anon.anonymized, project=self._project, k=k)
    context = "\n\n".join(hit.chunk for hit in result.hits)

    if llm is None:
        rehydrated = await self._svc.rehydrate(context, project=self._project, strict=False)
        return rehydrated.text

    prompt = _build_prompt(context=context, question=anon.anonymized)
    raw_answer = await llm.ainvoke(prompt)
    answer_text = raw_answer.content if hasattr(raw_answer, "content") else str(raw_answer)
    rehydrated = await self._svc.rehydrate(answer_text, project=self._project, strict=False)
    return rehydrated.text
```

Helper `_build_prompt(context, question)` returns a `ChatPromptTemplate.format_messages(...)` list with system + human messages. System prompt:

```
You are a helpful assistant. Answer the user's question based on the provided context.
The context and question contain opaque tokens of the form <LABEL:hash> (e.g., <PERSON:abc123>).
Preserve these tokens EXACTLY in your answer — do not expand, explain, or replace them.
If the context does not contain enough information, say "I don't know."
```

Strict rehydration defaults to `False` in the query path because LLM answers may legitimately contain new tokens (e.g., partial matches, tokens from context chunks). Users wanting strict mode can call `rag.rehydrator.invoke(answer, config={"strict": True})` manually.

### 2.3 `.retriever` — `BaseRetriever` wrapper

```python
from langchain_core.retrievers import BaseRetriever
from langchain_core.documents import Document


class _PIIGhostRetriever(BaseRetriever):
    svc: PIIGhostService
    project: str
    k: int = 5

    async def _aget_relevant_documents(self, query: str, *, run_manager=None) -> list[Document]:
        result = await self.svc.query(query, project=self.project, k=self.k)
        return [
            Document(
                page_content=hit.chunk,
                metadata={
                    "doc_id": hit.doc_id,
                    "file_path": hit.file_path,
                    "score": hit.score,
                    "rank": hit.rank,
                    "project": self.project,
                },
            )
            for hit in result.hits
        ]

    def _get_relevant_documents(self, query: str, *, run_manager=None) -> list[Document]:
        import asyncio
        return asyncio.run(self._aget_relevant_documents(query))
```

`.retriever` property returns `_PIIGhostRetriever(svc=self._svc, project=self._project)`.

### 2.4 `.as_chain`

```python
def as_chain(
    self,
    llm: "BaseLanguageModel",
    *,
    prompt: "Any | None" = None,
) -> "Runnable[str, str]":
    from langchain_core.runnables import RunnableLambda

    async def _run(question: str) -> str:
        return await self.query(question, llm=llm, prompt=prompt)

    return RunnableLambda(_run)
```

`query` gains a matching `prompt` keyword that overrides the default template when passed. Simple `RunnableLambda` wrapping `query`. Users who want fine-grained LCEL composition use `.anonymizer | .retriever | custom_prompt | llm | .rehydrator` directly.

## 3. Haystack wrapper — `build_piighost_rag`

### 3.1 `PIIGhostRetriever` component

```python
from haystack import component
from haystack.dataclasses import Document

from piighost.service.core import PIIGhostService


@component
class PIIGhostRetriever:
    def __init__(self, svc: PIIGhostService, *, project: str = "default", top_k: int = 5) -> None:
        self._svc = svc
        self._project = project
        self._top_k = top_k

    @component.output_types(documents=list[Document])
    def run(self, query: str, top_k: int | None = None) -> dict:
        from piighost.integrations.haystack._base import run_coroutine_sync
        return run_coroutine_sync(self._arun(query, top_k=top_k))

    @component.output_types(documents=list[Document])
    async def run_async(self, query: str, top_k: int | None = None) -> dict:
        return await self._arun(query, top_k=top_k)

    async def _arun(self, query: str, top_k: int | None) -> dict:
        k = top_k if top_k is not None else self._top_k
        result = await self._svc.query(query, project=self._project, k=k)
        docs = [
            Document(
                content=hit.chunk,
                meta={
                    "doc_id": hit.doc_id,
                    "file_path": hit.file_path,
                    "score": hit.score,
                    "rank": hit.rank,
                    "project": self._project,
                },
            )
            for hit in result.hits
        ]
        return {"documents": docs}
```

### 3.2 `build_piighost_rag` factory

```python
def build_piighost_rag(
    svc: PIIGhostService,
    *,
    project: str = "default",
    llm_generator: Any | None = None,
    top_k: int = 5,
) -> Pipeline:
    from haystack import Pipeline
    from haystack.components.builders import PromptBuilder
    from piighost.integrations.haystack.documents import PIIGhostQueryAnonymizer
    from piighost.integrations.haystack.rehydrator import PIIGhostRehydrator

    pipeline = Pipeline()
    pipeline.add_component("query_anonymizer", PIIGhostQueryAnonymizer(svc, project=project))
    pipeline.add_component("retriever", PIIGhostRetriever(svc, project=project, top_k=top_k))
    pipeline.add_component(
        "prompt_builder",
        PromptBuilder(template=_HAYSTACK_PROMPT_TEMPLATE),
    )
    if llm_generator is not None:
        pipeline.add_component("llm", llm_generator)
    pipeline.add_component("rehydrator", PIIGhostRehydrator(svc, project=project))

    pipeline.connect("query_anonymizer.query", "retriever.query")
    pipeline.connect("query_anonymizer.query", "prompt_builder.question")
    pipeline.connect("retriever.documents", "prompt_builder.documents")
    if llm_generator is not None:
        pipeline.connect("prompt_builder.prompt", "llm.prompt")
        pipeline.connect("llm.replies", "rehydrator.text")
    return pipeline


_HAYSTACK_PROMPT_TEMPLATE = """You are a helpful assistant. Answer based on the provided context.
Both the context and question contain opaque tokens like <LABEL:hash>. Preserve them exactly.

Context:
{% for doc in documents %}
{{ doc.content }}
{% endfor %}

Question: {{ question }}
"""
```

The `llm_generator` is optional so tests can build a pipeline without an LLM and assert the anonymizer → retriever → prompt_builder chain produces correct intermediate state.

**Note on existing `PIIGhostQueryAnonymizer` + `PIIGhostRehydrator`:** both already exist in the Haystack integration from prior sprints. Sprint 6a verifies they accept a `project` param (or adds one if missing) and wires them into the new pipeline.

## 4. Prompt templates

Both integrations ship minimal prompt templates emphasizing token preservation. Users can override:

```python
# LangChain: pass a custom PromptTemplate to as_chain
rag.as_chain(llm, prompt=my_custom_prompt)

# Haystack: replace the prompt_builder component
pipeline = build_piighost_rag(svc, llm_generator=my_llm)
pipeline.remove_component("prompt_builder")
pipeline.add_component("prompt_builder", MyCustomPromptBuilder())
pipeline.connect(...)
```

Default prompts are intentionally terse — the LLM's job is to answer, piighost's job is to keep PII private. We don't try to prompt-engineer answer quality.

## 5. Error handling

| Case | Behavior |
|------|----------|
| No PII detected in query | `anonymize` returns unchanged text. Retrieval runs on raw query. Rehydrate is a no-op. Correct. |
| No retrieval hits | Empty context passed to LLM. LLM typically says "I don't know." No exception. |
| Project doesn't exist | `svc.query(..., project=X)` raises `ProjectNotFound` (Sprint 5). Bubbles up verbatim. |
| LLM returns token not in vault | `rehydrate(..., strict=False)` returns text with token intact + `unknown_tokens` populated. `query()` returns the text as-is. Caller using `.rehydrator` directly with `strict=True` gets `PIISafetyViolation`. |
| LLM hallucinates raw PII | Out of scope for 6a — see Sprint 6b's post-hoc scan. Document as a known limitation. |
| LLM API failure | Whatever LangChain/Haystack raises, bubbles up. No retry logic. |

## 6. PII safety invariants (preserved)

- Raw PII never leaves `PIIGhostService`'s vault except as output of `rehydrate`. Retrieval returns anonymized chunks. LLM receives anonymized context + anonymized query.
- Wrapper adds no new code paths that access vault entries or original values. All PII access goes through `svc.rehydrate` or `svc.vault_show(reveal=True)`.
- End-to-end tests include a "fake LLM records every input" check that fails if raw PII ever reaches the LLM.

## 7. Testing

| Test | File | Purpose |
|------|------|---------|
| `test_hybrid_retrieval.py` fix | `tests/integrations/langchain/test_hybrid_retrieval.py` | Update import path so existing suite runs clean |
| `PIIGhostRAG` construction | `tests/integrations/langchain/test_rag.py` | `.ingest`, `.query`, `.anonymizer`, `.retriever`, `.rehydrator`, `.as_chain` all exist and have correct types |
| `PIIGhostRAG.query` with fake LLM | same | Fake LangChain LLM records input; assert raw PII absent; assert output contains rehydrated PII |
| `.retriever` returns documents | same | `retriever.invoke("Alice")` returns `list[Document]` scoped to the project |
| Haystack pipeline builds | `tests/integrations/haystack/test_rag_pipeline.py` | `build_piighost_rag(svc)` returns a `Pipeline` with expected components |
| Haystack end-to-end with fake generator | same | Pipeline run() produces rehydrated answer, fake generator logs no raw PII |
| E2E LangChain roundtrip | `tests/e2e/test_langchain_rag_roundtrip.py` | Ingest 2 fixture docs (with "Alice" + "Paris") → query → fake LLM → assert rehydrated answer contains "Alice" or "Paris" |
| E2E Haystack roundtrip | `tests/e2e/test_haystack_rag_roundtrip.py` | Same flow with Haystack Pipeline |
| PII zero-leak (both) | E2E tests | Fake LLM records all inputs; assert `"Alice"` / `"Paris"` never appeared in LLM input |

Skip-guards match existing patterns: `pytest.importorskip("langchain_core")` and `pytest.importorskip("haystack")` at module level.

## 8. Acceptance criteria

- `tests/integrations/langchain/test_hybrid_retrieval.py` passes with `langchain-community` installed.
- `PIIGhostRAG(svc).query("Alice is in Paris", llm=fake)` returns a non-empty rehydrated string.
- `build_piighost_rag(svc, llm_generator=fake).run({"query_anonymizer": {"text": "Alice?"}})` returns a rehydrated answer via the pipeline.
- Both E2E roundtrip tests pass with real LanceDB chunk store (stub detector is still OK — the test isn't about detection quality, it's about PII-preservation).
- PII-zero-leak tests assert raw `"Alice"` / `"Paris"` never appear in any LLM input.
- Full test suite (`tests/unit/ tests/e2e/ tests/integrations/`) passes with `uv sync --all-extras` installed, no import errors.

## 9. Out of scope (Sprint 6b)

- Cross-encoder reranking of retrieval results.
- Metadata filters on queries (label-scoped, date-range, etc.).
- Streaming answers.
- Answer caching (via aiocache, keyed on anonymized query hash + project).
- Post-hoc PII scan of LLM output to detect hallucinated PII.
- Benchmarks / quality evaluation harness.

Each of the above is substantial enough to warrant its own design iteration. Sprint 6a proves the wrapper works; 6b adds production polish.
