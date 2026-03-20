"""LangChain middleware for PII anonymization in agent conversations.

Intercepts the agent loop at three points:

* **abefore_model** – anonymises *all* messages (NER on human messages,
  string-replace on AI / tool messages) before the LLM sees them.
* **aafter_model** – deanonymises *all* messages so the user always sees
  real values in the conversation thread.
* **awrap_tool_call** – deanonymises tool-call arguments so tools receive
  real data, then re-anonymises the tool response before it goes back
  to the LLM.

All caching, hashing, and text-level replacement logic is delegated to
``AnonymizationPipeline``.  This class is a thin LangChain adapter.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from langchain.agents.middleware import AgentMiddleware, AgentState
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.runtime import Runtime
from langgraph.types import Command
from langgraph.typing import ContextT

from maskara.pipeline import AnonymizationPipeline

logger = logging.getLogger(__name__)


class PIIAnonymizationMiddleware(AgentMiddleware):
    """Anonymise PII transparently around the LLM / tool boundary.

    Args:
        pipeline: A configured ``AnonymizationPipeline`` (carries the
            anonymizer, labels, and store).

    Example:
        >>> from maskara.anonymizer.pipeline import AnonymizationPipeline
        >>> pipeline = AnonymizationPipeline(
        ...     anonymizer=anonymizer,
        ...     labels=["PERSON", "LOCATION"],
        ... )
        >>> middleware = PIIAnonymizationMiddleware(pipeline=pipeline)
        >>> agent = create_agent(
        ...     model="anthropic:claude-sonnet-4-20250514",
        ...     tools=[...],
        ...     middleware=[middleware],
        ... )
    """

    def __init__(self, pipeline: AnonymizationPipeline) -> None:
        super().__init__()
        self._pipeline = pipeline

    # -----------------------------------------------------------------
    # abefore_model – anonymise all messages
    # -----------------------------------------------------------------

    async def abefore_model(
        self,
        state: AgentState,
        runtime: Runtime[ContextT],
    ) -> dict[str, Any] | None:
        """Anonymise every message before the LLM sees the conversation.

        * ``HumanMessage`` – full NER detection via ``pipeline.anonymize``.
        * ``AIMessage`` / ``ToolMessage`` – fast string replacement via
          ``pipeline.reanonymize_text`` (covers values deanonymised by
          ``aafter_model`` on the previous turn).

        Args:
            state: The current agent state (contains ``messages``).
            runtime: The LangGraph runtime (unused but required by hook).

        Returns:
            An update dict replacing the ``messages`` key, or *None* if
            nothing changed.
        """
        changed = False
        messages = state["messages"]

        for idx, message in enumerate(messages):
            content = message.content
            if not isinstance(content, str) or not content.strip():
                raise ValueError("There are censed have Langchain message")

            if isinstance(message, (HumanMessage, AIMessage, ToolMessage)):
                result = await self._pipeline.anonymize(content)
                new_content = result.anonymized_text
            else:
                raise ValueError("There are censed have Langchain message")

            if new_content == content:
                continue

            if isinstance(message, (HumanMessage, AIMessage, ToolMessage)):
                messages[idx].content = new_content

            logger.debug(f"Anonymised message {idx}")
            changed = True

        return {"messages": messages} if changed else None

    # -----------------------------------------------------------------
    # aafter_model – deanonymise all messages for the user
    # -----------------------------------------------------------------

    async def aafter_model(
        self,
        state: AgentState,
        runtime: Runtime[ContextT],
    ) -> dict[str, Any] | None:
        """Deanonymise every message so the user sees real values.

        Args:
            state: The current agent state (contains ``messages``).
            runtime: The LangGraph runtime (unused but required by hook).

        Returns:
            An update dict replacing the ``messages`` key, or *None* if
            nothing changed.
        """
        messages = list(state["messages"])
        changed = False

        for idx, message in enumerate(messages):
            content = message.content
            if not isinstance(content, str) or not content.strip():
                continue

            restored = self._pipeline.deanonymize_text(content)
            if restored == content:
                continue

            if isinstance(message, HumanMessage):
                messages[idx] = HumanMessage(
                    content=restored,
                    **_preserve_metadata(message),
                )
            elif isinstance(message, AIMessage):
                messages[idx] = AIMessage(
                    content=restored,
                    tool_calls=message.tool_calls,
                    **_preserve_metadata(message),
                )
            elif isinstance(message, ToolMessage):
                messages[idx] = ToolMessage(
                    content=restored,
                    tool_call_id=message.tool_call_id,
                    name=message.name,
                )
            else:
                continue

            changed = True

        if changed:
            logger.debug(
                "Deanonymised %d message(s)", sum(1 for _ in range(len(messages)))
            )
        return {"messages": messages} if changed else None

    # -----------------------------------------------------------------
    # awrap_tool_call – deanonymise args → run tool → anonymise result
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
        # Deanonymise string arguments.
        call = request.tool_call
        args = call["args"]
        patched_args: dict[str, Any] = {}

        for arg_name, arg_value in args.items():
            if isinstance(arg_value, str):
                arg_value = self._pipeline.deanonymize_text(arg_value)
            patched_args[arg_name] = arg_value

        call["args"] = patched_args

        # Execute the tool.
        response = await handler(request)

        # Re-anonymise the tool response.
        if isinstance(response, ToolMessage) and isinstance(response.content, str):
            anonymized_content = self._pipeline.reanonymize_text(
                response.content,
            )
            return ToolMessage(
                content=anonymized_content,
                tool_call_id=response.tool_call_id,
                name=response.name,
            )

        return response


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _preserve_metadata(message: HumanMessage | AIMessage) -> dict[str, Any]:
    """Extract metadata fields to forward when re-creating a message.

    Args:
        message: The original message.

    Returns:
        A dict with ``id``, ``name`` etc.
    """
    meta: dict[str, Any] = {}
    if message.id is not None:
        meta["id"] = message.id
    if message.name is not None:
        meta["name"] = message.name
    return meta
