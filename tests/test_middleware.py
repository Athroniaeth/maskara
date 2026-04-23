"""Integration tests for PIIAnonymizationMiddleware with a fake LLM.

Tests a 3-turn conversation to verify:
- PII is anonymized before the LLM sees messages
- LLM responses are deanonymized for the user
- Tool arguments are deanonymized before execution
- Tool responses are re-anonymized before the LLM sees them
- The LLM NEVER sees real PII values
- ToolMessages are not double-encoded by abefore_model
"""

import pytest
from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver

from piighost.anonymizer import Anonymizer
from piighost.pipeline.thread import ThreadAnonymizationPipeline
from piighost.detector import ExactMatchDetector
from piighost.linker.entity import ExactEntityLinker
from piighost.resolver.entity import MergeEntityConflictResolver
from piighost.middleware import PIIAnonymizationMiddleware
from piighost.placeholder import (
    CounterPlaceholderFactory,
    MaskPlaceholderFactory,
    RedactPlaceholderFactory,
)
from piighost.resolver.span import ConfidenceSpanConflictResolver

# ---------------------------------------------------------------------------
# Spy infrastructure
# ---------------------------------------------------------------------------

_llm_received: list[list[str]] = []
_tool_calls_log: list[dict] = []


class SpyFakeChatModel(GenericFakeChatModel):
    """Fake model that records received messages and supports bind_tools."""

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        _llm_received.append(
            [m.content for m in messages if isinstance(m.content, str)]
        )
        return super()._generate(messages, stop, run_manager, **kwargs)


@tool
def get_weather(country_or_city: str) -> str:
    """Get the current weather for a given country or city."""
    _tool_calls_log.append({"country_or_city": country_or_city})
    return f"Il fait beau en {country_or_city}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_pipeline() -> ThreadAnonymizationPipeline:
    return ThreadAnonymizationPipeline(
        detector=ExactMatchDetector([("Patrick", "PERSON"), ("France", "LOCATION")]),
        span_resolver=ConfidenceSpanConflictResolver(),
        entity_linker=ExactEntityLinker(),
        entity_resolver=MergeEntityConflictResolver(),
        anonymizer=Anonymizer(CounterPlaceholderFactory()),
    )


# ---------------------------------------------------------------------------
# Integration test
# ---------------------------------------------------------------------------


class TestMiddlewareConversation:
    """Full 3-turn conversation through the PII middleware."""

    async def test_full_conversation_pii_flow(self) -> None:
        _llm_received.clear()
        _tool_calls_log.clear()

        responses = iter(
            [
                # Turn 1: text response with placeholders
                AIMessage(
                    content="Bonjour <<PERSON_1>>, que puis-je faire pour vous ?"
                ),
                # Turn 2: text response without placeholders
                AIMessage(
                    content="Desole, je ne peux pas vous donner cette information."
                ),
                # Turn 3a: tool call with placeholder in args
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "get_weather",
                            "args": {"country_or_city": "<<LOCATION_1>>"},
                            "id": "call_1",
                        }
                    ],
                ),
                # Turn 3b: final response after tool result
                AIMessage(content="Il fait 22C et ensoleille la ou vous habitez !"),
            ]
        )

        pipeline = _build_pipeline()
        middleware = PIIAnonymizationMiddleware(pipeline=pipeline)

        agent = create_agent(
            model=SpyFakeChatModel(messages=responses),
            tools=[get_weather],
            middleware=[middleware],
            checkpointer=InMemorySaver(),
        )
        config = {"configurable": {"thread_id": "test-pii"}}

        # -- Turn 1 ----------------------------------------------------------
        # User introduces themselves with PII (name + country).
        r1 = await agent.ainvoke(
            {
                "messages": [
                    HumanMessage(
                        content="Bonjour, je m'appelle Patrick, j'habite en France"
                    )
                ]
            },
            config,
        )
        last_content_1 = r1["messages"][-1].content
        # User sees deanonymized response.
        assert "Patrick" in last_content_1, (
            f"Expected 'Patrick' in user output: {last_content_1}"
        )

        # -- Turn 2 ----------------------------------------------------------
        # User asks something without new PII.
        r2 = await agent.ainvoke(
            {
                "messages": [
                    HumanMessage(content="Donne moi la premiere lettre de mon prenom")
                ]
            },
            config,
        )
        last_content_2 = r2["messages"][-1].content
        assert "Desole" in last_content_2

        # -- Turn 3 ----------------------------------------------------------
        # User asks for weather → triggers tool call.
        await agent.ainvoke(
            {"messages": [HumanMessage(content="Donne moi la meteo ou j'habite")]},
            config,
        )

        # Tool received the REAL value (deanonymized).
        assert len(_tool_calls_log) == 1, (
            f"Expected 1 tool call, got {len(_tool_calls_log)}"
        )
        assert _tool_calls_log[0]["country_or_city"] == "France", (
            f"Tool should receive 'France', got '{_tool_calls_log[0]['country_or_city']}'"
        )

        # -- Global assertion: LLM NEVER saw real PII -------------------------
        for idx, call_messages in enumerate(_llm_received):
            for content in call_messages:
                assert "Patrick" not in content, (
                    f"LLM call {idx} saw real PII 'Patrick' in: {content}"
                )
                assert "France" not in content, (
                    f"LLM call {idx} saw real PII 'France' in: {content}"
                )


class TestPipelineConversationFlow:
    """Simulate the middleware flow by calling pipeline methods directly.

    Reproduces the exact sequence of pipeline calls that the middleware
    performs, with explicit assertions on every intermediate value.
    """

    async def test_full_conversation(self) -> None:
        pipeline = _build_pipeline()

        # == Turn 1 ===========================================================
        # User: "Bonjour, je m'appelle Patrick, j'habite en France"

        # abefore_model: anonymize user message
        anonymized_1, _ = await pipeline.anonymize(
            "Bonjour, je m'appelle Patrick, j'habite en France"
        )
        assert (
            anonymized_1
            == "Bonjour, je m'appelle <<PERSON_1>>, j'habite en <<LOCATION_1>>"
        )

        # LLM responds (scripted) with placeholders
        llm_response_1 = "Bonjour <<PERSON_1>>, que puis-je faire pour vous ?"

        # aafter_model: deanonymize for user display
        user_sees_1 = await pipeline.deanonymize_with_ent(llm_response_1)
        assert user_sees_1 == "Bonjour Patrick, que puis-je faire pour vous ?"

        # == Turn 2 ===========================================================
        # User: "Donne moi la premiere lettre de mon prenom"

        # abefore_model: no PII to detect
        anonymized_2, _ = await pipeline.anonymize(
            "Donne moi la premiere lettre de mon prenom"
        )
        assert anonymized_2 == "Donne moi la premiere lettre de mon prenom"

        # LLM responds
        llm_response_2 = "Desole, je ne peux pas vous donner cette information."

        # aafter_model: nothing to deanonymize
        user_sees_2 = await pipeline.deanonymize_with_ent(llm_response_2)
        assert user_sees_2 == "Desole, je ne peux pas vous donner cette information."

        # == Turn 3 ===========================================================
        # User: "Donne moi la meteo ou j'habite"

        # abefore_model
        anonymized_3, _ = await pipeline.anonymize("Donne moi la meteo ou j'habite")
        assert anonymized_3 == "Donne moi la meteo ou j'habite"

        # LLM returns a tool call with placeholder arg
        tool_arg = "<<LOCATION_1>>"

        # awrap_tool_call: deanonymize arg for the tool
        tool_receives = await pipeline.deanonymize_with_ent(tool_arg)
        assert tool_receives == "France"

        # Tool executes with real value
        tool_result = f"Il fait beau en {tool_receives}"
        assert tool_result == "Il fait beau en France"

        # awrap_tool_call: re-anonymize tool response
        tool_result_anon, _ = await pipeline.anonymize(tool_result)
        assert tool_result_anon == "Il fait beau en <<LOCATION_1>>"

        # LLM receives anonymized tool result and responds
        llm_response_3 = "Il fait 22C et ensoleille la ou vous habitez !"

        # aafter_model: deanonymize for user display
        user_sees_3 = await pipeline.deanonymize_with_ent(llm_response_3)
        assert user_sees_3 == "Il fait 22C et ensoleille la ou vous habitez !"


class TestToolCallNoDoubleEncoding:
    """Verify that ToolMessages are not double-encoded by abefore_model.

    Regression test for a bug where abefore_model re-anonymized an
    already-anonymized ToolMessage, causing NER to detect the token
    text (e.g. ``city_1``) as PII and producing ``<<<<city_1>>>>``.
    This corrupted the entity memory and broke deanonymize_with_ent.
    """

    async def test_tool_response_deanonymized_after_tool_call(self) -> None:
        """After a tool call, the final AI response must be fully deanonymized."""
        _llm_received.clear()
        _tool_calls_log.clear()

        responses = iter(
            [
                # Turn 1a: tool call with placeholder arg
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "get_weather",
                            "args": {"country_or_city": "<<LOCATION_1>>"},
                            "id": "call_1",
                        }
                    ],
                ),
                # Turn 1b: final response referencing the placeholder
                AIMessage(
                    content="La meteo a <<LOCATION_1>> est de 22C et ensoleillee."
                ),
            ]
        )

        pipeline = _build_pipeline()
        middleware = PIIAnonymizationMiddleware(pipeline=pipeline)

        agent = create_agent(
            model=SpyFakeChatModel(messages=responses),
            tools=[get_weather],
            middleware=[middleware],
            checkpointer=InMemorySaver(),
        )
        config = {"configurable": {"thread_id": "test-tool-no-double"}}

        result = await agent.ainvoke(
            {"messages": [HumanMessage(content="Donne moi la meteo en France")]},
            config,
        )

        # Tool received real value
        assert _tool_calls_log[0]["country_or_city"] == "France"

        # Final AI response is fully deanonymized (not "LOCATION_1")
        last = result["messages"][-1].content
        assert "France" in last, f"Expected 'France' in final response: {last}"
        assert "LOCATION_1" not in last, f"Token leaked in response: {last}"

        # LLM never saw real PII
        for idx, call_messages in enumerate(_llm_received):
            for content in call_messages:
                assert "France" not in content, (
                    f"LLM call {idx} saw real PII 'France' in: {content}"
                )

    async def test_pipeline_no_double_encoding(self) -> None:
        """Simulate the middleware flow: re-anonymizing a ToolMessage must not corrupt entities."""
        pipeline = _build_pipeline()

        # abefore_model: anonymize user message
        anon, _ = await pipeline.anonymize("Donne moi la meteo en France")
        assert "<<LOCATION_1>>" in anon

        # awrap_tool_call: deanonymize arg → execute → re-anonymize response
        tool_arg = await pipeline.deanonymize_with_ent("<<LOCATION_1>>")
        assert tool_arg == "France"

        tool_result = f"Il fait beau en {tool_arg}"
        tool_anon, _ = await pipeline.anonymize(tool_result)
        assert tool_anon == "Il fait beau en <<LOCATION_1>>"

        # KEY: abefore_model must NOT re-process the ToolMessage.
        # If it did, anonymize("Il fait beau en <<LOCATION_1>>") would
        # detect "LOCATION_1" as PII and produce <<<<LOCATION_1>>>>.
        reanon, ents = await pipeline.anonymize("Il fait beau en <<LOCATION_1>>")

        # This documents the bug: NER detects the token text as an entity
        # and double-encodes it. The middleware fix skips ToolMessages
        # in abefore_model to avoid this.
        if reanon != "Il fait beau en <<LOCATION_1>>":
            # If this branch runs, it proves why skipping ToolMessages matters
            assert "<<" in reanon and ">>" in reanon

        # After the potential corruption above, deanonymize_with_ent on
        # the LLM response must still produce the correct real value.
        # Reset pipeline to test clean path (skip ToolMessage re-anonymization).
        clean_pipeline = _build_pipeline()
        await clean_pipeline.anonymize("Donne moi la meteo en France")

        # awrap_tool_call only
        await clean_pipeline.deanonymize_with_ent("<<LOCATION_1>>")
        tool_result_clean, _ = await clean_pipeline.anonymize("Il fait beau en France")

        # Do NOT re-anonymize the ToolMessage (middleware fix)
        # Directly deanonymize the LLM response
        llm_response = "La meteo a <<LOCATION_1>> est de 22C et ensoleillee."
        user_sees = await clean_pipeline.deanonymize_with_ent(llm_response)
        assert user_sees == "La meteo a France est de 22C et ensoleillee."


class TestNonReversibleFactoryRejected:
    """ThreadAnonymizationPipeline must reject non-reversible placeholder factories."""

    def test_redact_factory_raises(self) -> None:
        with pytest.raises(ValueError, match="RedactPlaceholderFactory"):
            ThreadAnonymizationPipeline(
                detector=ExactMatchDetector([("x", "PERSON")]),
                anonymizer=Anonymizer(RedactPlaceholderFactory()),
            )

    def test_mask_factory_raises(self) -> None:
        with pytest.raises(ValueError, match="MaskPlaceholderFactory"):
            ThreadAnonymizationPipeline(
                detector=ExactMatchDetector([("x", "PERSON")]),
                anonymizer=Anonymizer(MaskPlaceholderFactory()),
            )

    def test_counter_factory_accepted(self) -> None:
        ThreadAnonymizationPipeline(
            detector=ExactMatchDetector([("x", "PERSON")]),
            anonymizer=Anonymizer(CounterPlaceholderFactory()),
        )
