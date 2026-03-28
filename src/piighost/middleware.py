"""LangChain middleware for PII anonymization in agent conversations.

Intercepts the agent loop at three points:

* **abefore_model** anonymises *all* messages (NER on human messages,
  string-replace on AI / tool messages) before the LLM sees them.
* **aafter_model** deanonymises *all* messages so the user always sees
  real values in the conversation thread.
* **awrap_tool_call** deanonymises tool-call arguments so tools receive
  real data, then re-anonymises the tool response before it goes back
  to the LLM.

All caching, hashing, and text-level replacement logic is delegated to
``ThreadAnonymizationPipeline``.  This class is a thin LangChain adapter.
"""

import importlib.util

from piighost.pipeline.thread import ThreadAnonymizationPipeline

if importlib.util.find_spec("langchain") is None:
    raise ImportError(
        "You must install langchain to use PIIAnonymizationMiddleware, please install piighost[langchain] for use middleware"
    )

import logging
from typing import Any, Awaitable, Callable

from langchain.agents.middleware import AgentMiddleware, AgentState
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from piighost.exceptions import CacheMissError
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.runtime import Runtime
from langgraph.types import Command
from langgraph.typing import ContextT

logger = logging.getLogger(__name__)


class PIIAnonymizationMiddleware(AgentMiddleware):
    """Anonymise PII transparently around the LLM / tool boundary.

    Args:
        pipeline: A configured ``ConversationAnonymizationPipeline``
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

    def __init__(self, pipeline: ThreadAnonymizationPipeline) -> None:
        super().__init__()
        self._pipeline = pipeline

    async def abefore_model(
        self,
        state: AgentState,
        runtime: Runtime[ContextT],
    ) -> dict[str, Any] | None:
        """Anonymise every message before the LLM sees the conversation.

        * ``HumanMessage`` full NER detection via ``pipeline.anonymize``.
        * ``ToolMessage`` fast string replacement via
          ``pipeline.anonymize_with_ent`` (re-anonymises real values
          that tools returned).
        * ``AIMessage`` skipped the LLM already produces tokens.

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

            # This happens when the LLM uses a tool
            if not isinstance(content, str) or not content.strip():
                continue

            if isinstance(message, (HumanMessage, AIMessage, ToolMessage)):
                # Full NER detection for user input and tool can return new sensitive data..
                result, _ = await self._pipeline.anonymize(content)
            else:
                raise ValueError("This code only takes Langchain messages into account")

            if result == content:
                continue

            messages[idx].content = result

            logging.debug(f"Anonymised message {idx} : {result}")
            changed = True

        return {"messages": messages} if changed else None

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

            # This happens when the LLM uses a tool
            if not isinstance(content, str) or not content.strip():
                continue

            if not isinstance(message, (HumanMessage, AIMessage, ToolMessage)):
                raise ValueError("This code only takes Langchain messages into account")

            try:
                restored, _ = await self._pipeline.deanonymize(content)
            except CacheMissError:
                restored = await self._pipeline.deanonymize_with_ent(content)

            if restored == content:
                continue

            messages[idx].content = restored

            changed = True

        if changed:
            nbr_messages = len(messages)
            logging.debug(f"Deanonymised {nbr_messages} message(s)")

        return {"messages": messages} if changed else None

    # -----------------------------------------------------------------
    # awrap_tool_call deanonymise args → run tool → anonymise result
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
                try:
                    arg_value, _ = await self._pipeline.deanonymize(arg_value)
                except CacheMissError:
                    arg_value = await self._pipeline.deanonymize_with_ent(arg_value)
            patched_args[arg_name] = arg_value

        call["args"] = patched_args

        # Execute the tool.
        response = await handler(request)

        # Re-anonymise the tool response.
        if isinstance(response, ToolMessage) and isinstance(response.content, str):
            anonymized_content, _ = await self._pipeline.anonymize(response.content)
            response.content = anonymized_content
            return response

        return response
