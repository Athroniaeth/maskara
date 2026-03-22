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

import importlib.util

if importlib.util.find_spec("langchain") is None:
    raise ImportError(
        "You must install langchain to use PIIAnonymizationMiddleware, please install piighost[langchain] for use middleware"
    )

import logging
from typing import Any, Awaitable, Callable

from langchain.agents.middleware import AgentMiddleware, AgentState
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.runtime import Runtime
from langgraph.types import Command
from langgraph.typing import ContextT

from piighost.pipeline import AnonymizationPipeline

logger = logging.getLogger(__name__)


class PIIAnonymizationMiddleware(AgentMiddleware):
    """Anonymise PII transparently around the LLM / tool boundary.

    Args:
        pipeline: A configured ``AnonymizationPipeline`` (carries the
            anonymizer, labels, and store).

    Example:
        >>> from piighost.anonymizer.pipeline import AnonymizationPipeline
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
                # This happens when the LLM uses a tool
                continue

            if isinstance(message, (HumanMessage, AIMessage, ToolMessage)):
                result = await self._pipeline.anonymize(content)
                new_content = result.anonymized_text
            else:
                raise ValueError("This code only takes Langchain messages into account")

            if new_content == content:
                # This happens in the second message of a conversation
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
        changed = False
        messages = list(state["messages"])

        for idx, message in enumerate(messages):
            content = message.content

            if not isinstance(content, str) or not content.strip():
                # This happens when the LLM uses a tool
                continue

            restored = self._pipeline.deanonymize_text(content)

            if restored == content:
                continue

            if isinstance(message, (HumanMessage, AIMessage, ToolMessage)):
                messages[idx].content = restored
            else:
                raise ValueError("This code only takes Langchain messages into account")

            changed = True

        if changed:
            nbr_messages = sum(1 for _ in range(len(messages)))
            logger.debug(f"Deanonymised {nbr_messages} message(s)")
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
        # Deanonymise string arguments, provided by the LLM (which sees only anonymized entities)
        call = request.tool_call
        args = call["args"]
        patched_args: dict[str, Any] = {}

        for arg_name, arg_value in args.items():
            if isinstance(arg_value, str):
                arg_value = self._pipeline.deanonymize_value(arg_value)
            patched_args[arg_name] = arg_value

        call["args"] = patched_args

        # Execute the tool.
        response = await handler(request)

        # Re-anonymise the tool response.
        if isinstance(response, ToolMessage) and isinstance(response.content, str):
            anonymized_content = self._pipeline.reanonymize_text(response.content)
            response.content = anonymized_content
            return response

        return response
