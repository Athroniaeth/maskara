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
from enum import Enum
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
from piighost.placeholder_tags import PreservesIdentity

logger = logging.getLogger(__name__)


class ToolCallStrategy(Enum):
    """How the middleware handles tool-call inputs and outputs.

    Pick the strategy based on what the tool does with PII. The default
    ``FULL`` matches the middleware's historical behaviour.

    * ``FULL`` — deanonymise tool arguments before the tool runs and
      run the full pipeline on the tool response to re-anonymise any
      new PII it may contain. Use for tools that fetch or return
      potentially sensitive data (databases, search APIs, CRMs).

    * ``INBOUND_ONLY`` — deanonymise arguments, but pass the tool
      response through unchanged. The next ``abefore_model`` pass will
      anonymise it on its way back to the LLM. Cheaper when the tool
      response is known to be PII-free or when re-detection would be
      wasteful.

    * ``PASSTHROUGH`` — never touch tool calls. Tools receive the
      placeholder tokens verbatim and return whatever they produce.
      Use for agents whose tools must never see real PII (strict
      privacy boundary) or agents with no PII-sensitive tools.

    Notes:
        The choice of :class:`AnyPlaceholderFactory` interacts with
        this setting. ``LabelHashPlaceholderFactory`` is the safest because
        placeholders are deterministic and collision-resistant.
        ``LabelCounterPlaceholderFactory`` is safe within a thread.
        ``LabelPlaceholderFactory`` and ``MaskPlaceholderFactory`` are
        rejected upstream by ``ThreadAnonymizationPipeline`` because
        they produce non-unique tokens. A ``FakerPlaceholderFactory``
        can in theory collide with real values present in tool
        responses; prefer hash-based placeholders if that matters.
    """

    FULL = "full"
    INBOUND_ONLY = "inbound_only"
    PASSTHROUGH = "passthrough"


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
        tool_strategy: How to handle tool calls. Defaults to
            :attr:`ToolCallStrategy.FULL` (current historical
            behaviour). See :class:`ToolCallStrategy` for the full
            trade-offs.

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

    _pipeline: ThreadAnonymizationPipeline[PreservesIdentity]
    tool_strategy: ToolCallStrategy

    def __init__(
        self,
        pipeline: ThreadAnonymizationPipeline[PreservesIdentity],
        tool_strategy: ToolCallStrategy = ToolCallStrategy.FULL,
    ) -> None:
        super().__init__()
        self._pipeline = pipeline
        self.tool_strategy = tool_strategy

    async def abefore_model(
        self,
        state: AgentState,
        runtime: Runtime[ContextT],
    ) -> dict[str, Any] | None:
        """Anonymise ``HumanMessage`` and ``AIMessage`` content.

        ``ToolMessage`` is skipped in ``FULL`` and ``PASSTHROUGH`` modes
        because the content is already anonymised (FULL) or the user
        opted out of tool protection (PASSTHROUGH). In ``INBOUND_ONLY``,
        the ``ToolMessage`` is processed here so the LLM never sees
        raw PII that a tool may have returned.

        Args:
            state: The current agent state (contains ``messages``).
            runtime: The LangGraph runtime (unused but required by hook).

        Returns:
            An update dict replacing the ``messages`` key, or *None* if
            nothing changed.
        """
        pipeline = self._pipeline
        thread_id = _get_thread_id()

        allowed_types: tuple[type, ...] = (HumanMessage, AIMessage)
        if self.tool_strategy is ToolCallStrategy.INBOUND_ONLY:
            # awrap_tool_call left the ToolMessage raw; catch it here so
            # the LLM never sees real PII on the next pass.
            allowed_types = (HumanMessage, AIMessage, ToolMessage)

        changed = False
        messages = state["messages"]

        for idx, message in enumerate(messages):
            if not isinstance(message, allowed_types):
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
        """Route the tool call according to the configured strategy.

        See :class:`ToolCallStrategy` for the semantics of each variant.

        Args:
            request: A ``ToolCallRequest`` carrying ``call``, ``tool``,
                ``state``, and ``runtime``.
            handler: Async callable that actually runs the tool.

        Returns:
            A ``ToolMessage`` (or ``Command``) processed according to
            the active strategy.
        """
        if self.tool_strategy is ToolCallStrategy.PASSTHROUGH:
            return await handler(request)

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

        if self.tool_strategy is ToolCallStrategy.FULL and (
            isinstance(response, ToolMessage) and isinstance(response.content, str)
        ):
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
