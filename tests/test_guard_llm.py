"""Tests for ``LLMGuardRail`` using mock chat models.

Mirrors ``tests/detector/test_llm_detector.py``: we stub
``langchain_core`` and ``pydantic`` so the suite runs without the
optional ``langchain`` extra installed.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest


class _FakeRunnable:
    def __init__(self, result: object) -> None:
        self._result = result

    async def ainvoke(self, input: object) -> object:  # noqa: A002
        return self._result


class _FakeChatModel:
    def __init__(self, result: object) -> None:
        self._result = result

    def with_structured_output(self, schema: object) -> _FakeRunnable:
        return _FakeRunnable(self._result)


def _entity(text: str, label: str) -> SimpleNamespace:
    return SimpleNamespace(text=text, label=SimpleNamespace(value=label))


def _extraction(*entities: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(entities=list(entities))


@pytest.fixture
def _patch_langchain_core(monkeypatch):
    import sys
    import types

    fake_lc = types.ModuleType("langchain_core")
    fake_lm = types.ModuleType("langchain_core.language_models")
    fake_lm.BaseChatModel = _FakeChatModel  # type: ignore[attr-defined]
    fake_lc.language_models = fake_lm  # type: ignore[attr-defined]

    fake_msg = types.ModuleType("langchain_core.messages")

    class _Msg:
        def __init__(self, content: str) -> None:
            self.content = content

    fake_msg.SystemMessage = _Msg  # type: ignore[attr-defined]
    fake_msg.HumanMessage = _Msg  # type: ignore[attr-defined]
    fake_lc.messages = fake_msg  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "langchain_core", fake_lc)
    monkeypatch.setitem(sys.modules, "langchain_core.language_models", fake_lm)
    monkeypatch.setitem(sys.modules, "langchain_core.messages", fake_msg)

    if "pydantic" not in sys.modules:

        class _FakeBaseModel:
            pass

        fake_pydantic = types.ModuleType("pydantic")
        fake_pydantic.BaseModel = _FakeBaseModel  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "pydantic", fake_pydantic)

    original = __import__("importlib.util").util.find_spec

    def patched_find_spec(name, *args, **kwargs):
        if name == "langchain_core":
            return True
        return original(name, *args, **kwargs)

    monkeypatch.setattr("importlib.util.find_spec", patched_find_spec)


def _get_guard_class():
    """Re-import ``LLMGuardRail`` after the langchain_core stubs are in place."""
    import importlib
    import sys

    sys.modules.pop("piighost.guard_llm", None)
    sys.modules.pop("piighost.detector.llm", None)
    mod = importlib.import_module("piighost.guard_llm")
    return mod.LLMGuardRail


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestLLMGuardRail:
    """LLMGuardRail flags residual clear-text PII reported by the model."""

    @pytest.mark.asyncio
    async def test_passes_when_llm_reports_nothing(self, _patch_langchain_core) -> None:
        LLMGuardRail = _get_guard_class()
        model = _FakeChatModel(_extraction())  # empty list
        guard = LLMGuardRail(model=model, labels=["PERSON"])

        await guard.check("All clean here, just <<PERSON:1>>.")

    @pytest.mark.asyncio
    async def test_raises_when_llm_reports_residual(
        self, _patch_langchain_core
    ) -> None:
        from piighost.exceptions import PIIRemainingError

        LLMGuardRail = _get_guard_class()
        model = _FakeChatModel(_extraction(_entity("Marie", "PERSON")))
        guard = LLMGuardRail(model=model, labels=["PERSON"])

        with pytest.raises(PIIRemainingError) as exc_info:
            await guard.check("Hello <<PERSON:1>>, also Marie is here.")

        residual = exc_info.value.detections
        assert any(d.text == "Marie" and d.label == "PERSON" for d in residual)

    @pytest.mark.asyncio
    async def test_residual_count_in_message(self, _patch_langchain_core) -> None:
        from piighost.exceptions import PIIRemainingError

        LLMGuardRail = _get_guard_class()
        model = _FakeChatModel(
            _extraction(
                _entity("Marie", "PERSON"),
                _entity("Lyon", "LOCATION"),
            ),
        )
        guard = LLMGuardRail(model=model, labels=["PERSON", "LOCATION"])

        with pytest.raises(PIIRemainingError) as exc_info:
            await guard.check("Hello <<PERSON:1>>, Marie lives in Lyon.")

        assert "2 residual" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_hallucinated_entity_is_silently_dropped(
        self, _patch_langchain_core
    ) -> None:
        """If the LLM invents an entity that is not in the text, the
        underlying ``LLMDetector`` returns no occurrence and the guard
        passes."""
        LLMGuardRail = _get_guard_class()
        # The model claims "Sophie" is in the text, but it is not.
        model = _FakeChatModel(_extraction(_entity("Sophie", "PERSON")))
        guard = LLMGuardRail(model=model, labels=["PERSON"])

        await guard.check("Only <<PERSON:1>> is mentioned here.")
