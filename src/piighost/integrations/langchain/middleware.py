"""LangChain middleware for PII anonymization in agent conversations.

Intercepts the agent loop at three points:

* **abefore_model** anonymises ``HumanMessage`` and ``AIMessage``
  content before the LLM sees them.  ``ToolMessage`` content is
  skipped — it is already anonymised by ``awrap_tool_call``.
* **aafter_model** deanonymises ``HumanMessage`` and ``AIMessage``
  content so the user always sees real values in the conversation
  thread.  ``ToolMessage`` content stays anonymised.
* **awrap_tool_call** deanonymises tool-call arguments so tools
  receive real data, then re-anonymises the tool response before it
  goes back to the LLM.

All caching, hashing, and text-level replacement logic is delegated to
``ThreadAnonymizationPipeline``.  This class is a thin LangChain adapter.
"""

import importlib.util

if importlib.util.find_spec("langchain") is None:
    raise ImportError(
        "You must install langchain to use PIIAnonymizationMiddleware, "
        "please install piighost[middleware]"
    )

import logging
from typing import Any, Awaitable, Callable

from langchain.agents.middleware import AgentMiddleware, AgentState
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.config import get_config
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.runtime import Runtime
from langgraph.types import Command
from langgraph.typing import ContextT

from piighost.exceptions import CacheMissError
from piighost.pipeline.thread import ThreadAnonymizationPipeline

logger = logging.getLogger(__name__)


def _get_thread_id() -> str:
    """Extract the thread id from the LangGraph runtime config.

    Falls back to ``"default"`` when called outside a runnable context
    or on Python < 3.11 where ``get_config()`` is unavailable in async.
    """
    try:
        return get_config().get("configurable", {}).get("thread_id", "default")
    except RuntimeError:
        return "default"


class PIIAnonymizationMiddleware(AgentMiddleware):
    """Anonymise PII transparently around the LLM / tool boundary.

    Args:
        pipeline: A configured ``ThreadAnonymizationPipeline``
            (wraps the base pipeline with conversation memory).

    Example:
        >>> from piighost.pipeline.thread import ThreadAnonymizationPipeline
        >>> conv_pipeline = ThreadAnonymizationPipeline(pipeline=base, ph_factory=factory)
        >>> middleware = PIIAnonymizationMiddleware(pipeline=conv_pipeline)
        >>> agent = create_agent(
        ...     model="anthropic:claude-sonnet-4-20250514",
        ...     tools=[...],
        ...     middleware=[middleware],
        ... )
    """

    _pipeline: ThreadAnonymizationPipeline

    def __init__(self, pipeline: ThreadAnonymizationPipeline) -> None:
        super().__init__()
        self._pipeline = pipeline

    async def abefore_model(
        self,
        state: AgentState,
        runtime: Runtime[ContextT],
    ) -> dict[str, Any] | None:
        """Anonymise ``HumanMessage`` and ``AIMessage`` content.

        ``ToolMessage`` is skipped — tools already operate on anonymised
        tokens, so their responses already contain placeholders.

        Args:
            state: The current agent state (contains ``messages``).
            runtime: The LangGraph runtime (unused but required by hook).

        Returns:
            An update dict replacing the ``messages`` key, or *None* if
            nothing changed.
        """
        pipeline = self._pipeline
        thread_id = _get_thread_id()

        changed = False
        messages = state["messages"]

        for idx, message in enumerate(messages):
            if not isinstance(message, (HumanMessage, AIMessage)):
                continue

            content = message.content

            if not isinstance(content, str) or not content.strip():
                continue

            result, ents = await pipeline.anonymize(content, thread_id=thread_id)

            logger.debug(
                "[PII] msg %d (%s) content=%r → result=%r entities=%s",
                idx,
                type(message).__name__,
                content[:80],
                result[:80],
                [(e.detections[0].text, e.label, len(e.detections)) for e in ents],
            )

            if result == content:
                continue

            messages[idx].content = result
            changed = True

        return {"messages": messages} if changed else None

    async def aafter_model(
        self,
        state: AgentState,
        runtime: Runtime[ContextT],
    ) -> dict[str, Any] | None:
        """Deanonymise ``HumanMessage`` and ``AIMessage`` content.

        ``ToolMessage`` is left anonymised — it is not shown to the user
        and the LLM already expects tokens in tool responses.

        Args:
            state: The current agent state (contains ``messages``).
            runtime: The LangGraph runtime (unused but required by hook).

        Returns:
            An update dict replacing the ``messages`` key, or *None* if
            nothing changed.
        """
        thread_id = _get_thread_id()

        changed = False
        messages = state["messages"]

        for idx, message in enumerate(messages):
            if not isinstance(message, (HumanMessage, AIMessage)):
                continue

            content = message.content

            if not isinstance(content, str) or not content.strip():
                continue

            restored = await self._deanonymize(content, thread_id=thread_id)

            if restored == content:
                continue

            messages[idx].content = restored
            changed = True

        return {"messages": messages} if changed else None

    # -----------------------------------------------------------------
    # awrap_tool_call — deanonymise args, run tool, re-anonymise result
    # -----------------------------------------------------------------

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        """Deanonymise tool arguments, execute, and re-anonymise the result.

        Args:
            request: A ``ToolCallRequest`` carrying ``call``, ``tool``,
                ``state``, and ``runtime``.
            handler: Async callable that actually runs the tool.

        Returns:
            A ``ToolMessage`` (or ``Command``) with re-anonymised content.
        """
        thread_id = _get_thread_id()

        call = request.tool_call
        args = call["args"]
        patched_args: dict[str, Any] = {}

        for arg_name, arg_value in args.items():
            if isinstance(arg_value, str):
                arg_value = await self._deanonymize(arg_value, thread_id=thread_id)
            patched_args[arg_name] = arg_value

        call["args"] = patched_args
        response = await handler(request)

        if isinstance(response, ToolMessage) and isinstance(response.content, str):
            anonymized_content, _ = await self._pipeline.anonymize(
                response.content, thread_id=thread_id
            )
            response.content = anonymized_content

        return response

    # -----------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------

    async def _deanonymize(self, text: str, thread_id: str = "default") -> str:
        """Deanonymise text, falling back to entity-based replacement.

        Tries cache-based deanonymisation first (exact original text).
        Falls back to ``deanonymize_with_ent`` for text never seen by
        the pipeline (e.g. LLM-generated responses containing tokens).
        """
        try:
            result, _ = await self._pipeline.deanonymize(text, thread_id=thread_id)
        except CacheMissError:
            result = await self._pipeline.deanonymize_with_ent(
                text, thread_id=thread_id
            )
        return result
