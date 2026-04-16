"""Tests for LLMDetector using mock LLM models."""

from __future__ import annotations

from types import SimpleNamespace

import pytest


# ---------------------------------------------------------------------------
# Lightweight fakes that mimic langchain_core interfaces so we don't
# need langchain-core installed to run these tests.
# ---------------------------------------------------------------------------


class _FakeRunnable:
    """Mimics the runnable returned by ``with_structured_output``."""

    def __init__(self, result: object) -> None:
        self._result = result

    async def ainvoke(self, input: object) -> object:  # noqa: A002
        return self._result


class _FakeChatModel:
    """Mimics ``BaseChatModel.with_structured_output().ainvoke()``."""

    def __init__(self, result: object) -> None:
        self._result = result

    def with_structured_output(self, schema: object) -> _FakeRunnable:
        return _FakeRunnable(self._result)


def _entity(text: str, label: str) -> SimpleNamespace:
    """Build a fake entity matching the ``_Extraction`` schema structure."""
    return SimpleNamespace(text=text, label=SimpleNamespace(value=label))


def _extraction(*entities: SimpleNamespace) -> SimpleNamespace:
    """Build a fake ``_Extraction`` result."""
    return SimpleNamespace(entities=list(entities))


# ---------------------------------------------------------------------------
# Import helper – patches importlib so the guard in llm.py passes even
# when langchain-core is not installed.
# ---------------------------------------------------------------------------


@pytest.fixture
def _patch_langchain_core(monkeypatch):
    """Make ``importlib.util.find_spec("langchain_core")`` return a truthy
    value and inject fake ``langchain_core`` / ``pydantic`` modules so the
    detector can be imported without any optional dependency installed."""
    import sys
    import types

    # -- fake langchain_core.language_models ---------------------
    fake_lc = types.ModuleType("langchain_core")
    fake_lm = types.ModuleType("langchain_core.language_models")
    fake_lm.BaseChatModel = _FakeChatModel  # type: ignore[attr-defined]
    fake_lc.language_models = fake_lm  # type: ignore[attr-defined]

    # -- fake langchain_core.messages ----------------------------
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

    # -- fake pydantic (only if not already installed) -----------
    # _make_schema creates Pydantic BaseModel subclasses, but the tests
    # never instantiate them (the fake model ignores the schema).  A
    # minimal stub that supports subclassing is sufficient.
    if "pydantic" not in sys.modules:

        class _FakeBaseModel:
            """Minimal stand-in for ``pydantic.BaseModel``."""

        fake_pydantic = types.ModuleType("pydantic")
        fake_pydantic.BaseModel = _FakeBaseModel  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "pydantic", fake_pydantic)

    original = __import__("importlib.util").util.find_spec

    def patched_find_spec(name, *args, **kwargs):
        if name == "langchain_core":
            return True  # truthy sentinel
        return original(name, *args, **kwargs)

    monkeypatch.setattr("importlib.util.find_spec", patched_find_spec)


def _get_detector_class():
    """Import ``LLMDetector`` (must be called inside a test using
    the ``_patch_langchain_core`` fixture)."""
    import importlib
    import sys

    # Remove cached module so re-import picks up the patched modules.
    sys.modules.pop("piighost.detector.llm", None)
    mod = importlib.import_module("piighost.detector.llm")
    return mod.LLMDetector


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBasicDetection:
    @pytest.mark.asyncio
    async def test_single_entity(self, _patch_langchain_core):
        LLMDetector = _get_detector_class()
        model = _FakeChatModel(_extraction(_entity("Patrick", "PERSON")))
        detector = LLMDetector(model=model, labels=["PERSON"])

        detections = await detector.detect("Patrick habite à Paris")

        assert len(detections) == 1
        assert detections[0].text == "Patrick"
        assert detections[0].label == "PERSON"
        assert detections[0].position.start_pos == 0
        assert detections[0].position.end_pos == 7
        assert detections[0].confidence == 1.0

    @pytest.mark.asyncio
    async def test_multiple_entities(self, _patch_langchain_core):
        LLMDetector = _get_detector_class()
        model = _FakeChatModel(
            _extraction(
                _entity("Patrick", "PERSON"),
                _entity("Paris", "LOCATION"),
            ),
        )
        detector = LLMDetector(model=model, labels=["PERSON", "LOCATION"])

        detections = await detector.detect("Patrick habite à Paris")

        assert len(detections) == 2
        texts = {d.text for d in detections}
        assert texts == {"Patrick", "Paris"}

    @pytest.mark.asyncio
    async def test_no_entities(self, _patch_langchain_core):
        LLMDetector = _get_detector_class()
        model = _FakeChatModel(_extraction())
        detector = LLMDetector(model=model, labels=["PERSON"])

        detections = await detector.detect("Bonjour le monde")

        assert detections == []

    @pytest.mark.asyncio
    async def test_empty_text(self, _patch_langchain_core):
        LLMDetector = _get_detector_class()
        model = _FakeChatModel(_extraction())
        detector = LLMDetector(model=model, labels=["PERSON"])

        detections = await detector.detect("")

        assert detections == []


class TestMultipleOccurrences:
    @pytest.mark.asyncio
    async def test_finds_all_occurrences(self, _patch_langchain_core):
        """LLM returns one entity, but it appears twice in the text."""
        LLMDetector = _get_detector_class()
        model = _FakeChatModel(_extraction(_entity("Patrick", "PERSON")))
        detector = LLMDetector(model=model, labels=["PERSON"])

        detections = await detector.detect("Patrick est gentil. Patrick habite ici.")

        assert len(detections) == 2
        positions = [(d.position.start_pos, d.position.end_pos) for d in detections]
        assert (0, 7) in positions
        assert (20, 27) in positions

    @pytest.mark.asyncio
    async def test_case_insensitive_occurrences(self, _patch_langchain_core):
        """Word-boundary matching is case-insensitive by default."""
        LLMDetector = _get_detector_class()
        model = _FakeChatModel(_extraction(_entity("Patrick", "PERSON")))
        detector = LLMDetector(model=model, labels=["PERSON"])

        detections = await detector.detect("Patrick dit bonjour. patrick aussi.")

        assert len(detections) == 2


class TestHallucination:
    @pytest.mark.asyncio
    async def test_hallucinated_entity_ignored(self, _patch_langchain_core):
        """LLM returns an entity not present in the text."""
        LLMDetector = _get_detector_class()
        model = _FakeChatModel(_extraction(_entity("Jean", "PERSON")))
        detector = LLMDetector(model=model, labels=["PERSON"])

        detections = await detector.detect("Patrick habite à Paris")

        assert detections == []

    @pytest.mark.asyncio
    async def test_mix_real_and_hallucinated(self, _patch_langchain_core):
        """Real entities are kept, hallucinated ones are discarded."""
        LLMDetector = _get_detector_class()
        model = _FakeChatModel(
            _extraction(
                _entity("Patrick", "PERSON"),
                _entity("Lyon", "LOCATION"),
            ),
        )
        detector = LLMDetector(model=model, labels=["PERSON", "LOCATION"])

        detections = await detector.detect("Patrick habite à Paris")

        assert len(detections) == 1
        assert detections[0].text == "Patrick"


class TestCustomPrompt:
    @pytest.mark.asyncio
    async def test_custom_prompt_accepted(self, _patch_langchain_core):
        """A custom prompt template with {labels} placeholder works."""
        LLMDetector = _get_detector_class()
        model = _FakeChatModel(_extraction(_entity("Patrick", "PERSON")))
        detector = LLMDetector(
            model=model,
            labels=["PERSON"],
            prompt="Custom extraction prompt for: {labels}",
        )

        detections = await detector.detect("Patrick est ici")

        assert len(detections) == 1
        assert detections[0].text == "Patrick"
