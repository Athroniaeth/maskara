"""PII anonymization middleware backed by GLiNER2 zero-shot NER."""

from __future__ import annotations

import hashlib
import re
from typing import Annotated, Any, Awaitable, Callable

from gliner2 import GLiNER2
from langchain.agents.middleware import (
    AgentMiddleware,
    AgentState,
)
from langchain.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain.tools.tool_node import ToolCallRequest
from langchain_core.messages import ToolCall
from langgraph.runtime import Runtime
from langgraph.types import Command
from loguru import logger

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"<[A-Z_]+:[0-9a-f]{8}>")

# Maps GLiNER label → entity type used in tokens.
_ENTITY_LABELS: dict[str, str] = {
    "person": "PERSON",
    "location": "LOCATION",
    "organization": "ORGANIZATION",
    "email address": "EMAIL_ADDRESS",
    "phone number": "PHONE_NUMBER",
}

_DEFAULT_FIELDS: list[str] = list(_ENTITY_LABELS.values())


# ---------------------------------------------------------------------------
# State schema
# ---------------------------------------------------------------------------


def _merge_dicts(a: dict, b: dict) -> dict:
    """Merge two dicts, with *b* entries taking precedence.

    Args:
        a: Base dictionary.
        b: Dictionary with new or updated entries.

    Returns:
        Combined dictionary.
    """
    return {**a, **b}


class PIIState(AgentState):
    """Extended agent state that persists the PII token mapping across turns.

    LangGraph checkpoints this state, so the bidirectional mapping survives
    across all hook invocations and conversation turns.

    Attributes:
        pii_to_token: Maps each original PII string to its anonymized token.
        pii_to_original: Maps each token back to the original PII string.
    """

    pii_to_token: Annotated[dict[str, str], _merge_dicts]
    pii_to_original: Annotated[dict[str, str], _merge_dicts]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _short_hash(value: str) -> str:
    """Return the first 8 hex characters of the SHA-256 digest of *value*.

    Args:
        value: The string to hash.

    Returns:
        An 8-character lowercase hex string.
    """
    return hashlib.sha256(value.encode()).hexdigest()[:8]


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------


class PIIAnonymizationMiddleware(AgentMiddleware):
    """Anonymize PII in LLM calls using GLiNER2 zero-shot named entity recognition.

    The bidirectional token mapping is stored in :class:`PIIState` and persisted
    by LangGraph's checkpointer, so the same token is always used for the same
    original value across all hooks and conversation turns.

    Flow:
        - ``before_model``: anonymize new human messages and tool results in
          state before the LLM sees them.  Re-apply known mappings to AI messages
          that were deanonymized by ``after_agent``.
        - ``wrap_tool_call``: deanonymize tool arguments so the tool runs with
          real data.  The raw tool result is stored in state; ``before_model``
          will anonymize it on the next model call.
        - ``after_agent``: deanonymize the final AI message so the user sees
          real values.

    Example:
        .. code-block:: python

            from aegra.middleware import PIIAnonymizationMiddleware, PIIState
            from langchain.agents import create_agent

            graph = create_agent(
                model="openai:gpt-4o",
                state_schema=PIIState,
                tools=[...],
                middleware=[PIIAnonymizationMiddleware()],
            )
    """

    def __init__(
        self,
        analyzed_fields: list[str] | None = None,
        gliner_model: str = "fastino/gliner2-large-v1",
        threshold: float = 0.4,
        language: str = "fr",
    ) -> None:
        """Initialize the middleware.

        Args:
            analyzed_fields: Entity types to detect and anonymize.  Defaults to
                PERSON, LOCATION, ORGANIZATION, EMAIL_ADDRESS, PHONE_NUMBER.
            gliner_model: HuggingFace model ID for GLiNER2.
            threshold: Minimum confidence score for an entity to be anonymized.
                Lower values catch more entities but increase false positives.
            language: Language code passed to the NER model (e.g. ``"fr"``).
        """
        super().__init__()

        self._language = language
        self._threshold = threshold
        self._analyzed_fields = analyzed_fields or _DEFAULT_FIELDS

        # Only pass labels whose entity type is requested.
        self._labels: list[str] = [
            label
            for label, entity in _ENTITY_LABELS.items()
            if entity in self._analyzed_fields
        ]

        logger.info("Loading GLiNER2 model: {}", gliner_model)
        self._model: GLiNER2 = GLiNER2.from_pretrained(gliner_model)

        # In-memory cache — synced from state at the start of each hook call.
        self._to_token: dict[str, str] = {}
        self._to_original: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def anonymize(self, text: str) -> str:
        """Detect PII in *text* and replace each span with a deterministic token.

        Relies on ``_to_token`` / ``_to_original`` being synced from state
        before this method is called (see :meth:`_sync_from_state`).

        Args:
            text: Raw text potentially containing PII.

        Returns:
            Text with all detected PII replaced by ``<ENTITY_TYPE:xxxxxxxx>``
            tokens.
        """
        if not text or not self._labels:
            return text

        # 1. Replace already-known original values using the cached mapping.
        for original, token in self._to_token.items():
            text = text.replace(original, token)

        # 2. Mask existing tokens with null-byte placeholders so GLiNER cannot
        #    re-detect them and create nested tokens.
        placeholders: dict[str, str] = {}

        def _mask(m: re.Match) -> str:
            key = f"\x00{len(placeholders)}\x00"
            placeholders[key] = m.group(0)
            return key

        text = _TOKEN_RE.sub(_mask, text)

        # 3. Run GLiNER2 to detect new PII spans.
        raw = self._model.extract_entities(
            text,
            self._labels,
            threshold=self._threshold,
            include_spans=True,
            include_confidence=True,
        )

        hits: list[tuple[int, int, str]] = []
        for label, entities in raw.get("entities", {}).items():
            entity_type = _ENTITY_LABELS.get(label)
            if entity_type is None or entity_type not in self._analyzed_fields:
                continue
            for entity in entities:
                hits.append((entity["start"], entity["end"], entity_type))

        # Sort descending so replacing later spans doesn't shift earlier indices.
        hits.sort(key=lambda h: h[0], reverse=True)

        for start, end, entity_type in hits:
            span = text[start:end]
            original = span.strip()
            if not original:
                continue
            # Narrow boundaries to stripped content so "Lyon " and "Lyon" share
            # the same key in _to_token.
            actual_start = start + len(span) - len(span.lstrip())
            actual_end = end - (len(span) - len(span.rstrip()))
            token = self._get_or_create_token(original, entity_type)
            text = text[:actual_start] + token + text[actual_end:]

        # 4. Restore masked tokens.
        for ph, token in placeholders.items():
            text = text.replace(ph, token)

        return text

    def deanonymize(self, text: str) -> str:
        """Replace all tokens in *text* with their original values.

        Args:
            text: Text containing ``<ENTITY_TYPE:xxxxxxxx>`` tokens.

        Returns:
            Text with tokens replaced by their original PII values.
        """
        for token, original in self._to_original.items():
            text = text.replace(token, original)
        return text

    # ------------------------------------------------------------------
    # Middleware hooks
    # ------------------------------------------------------------------

    def before_model(
        self,
        state: PIIState,
        runtime: Runtime,
    ) -> dict[str, Any] | None:
        """Anonymize new messages in state before they reach the LLM.

        Processes:

        - **Last HumanMessage**: full GLiNER2 anonymization.
        - **ToolMessages after the last AIMessage**: full GLiNER2 anonymization
          (tool results stored raw by ``wrap_tool_call``).
        - **AIMessages**: step-1 only — re-apply known mappings to restore any
          content deanonymized by ``after_agent`` without running GLiNER2.

        Args:
            state: Current agent state including the PII mapping.
            runtime: LangGraph runtime (unused).

        Returns:
            State patch with updated messages and new mapping entries, or
            ``None`` if nothing changed.
        """
        self._sync_from_state(state)

        messages = state.get("messages") or []
        if not messages:
            return None

        snapshot_to_token = dict(self._to_token)

        new_messages = list(messages)
        any_modified = False

        # Locate last AIMessage index (used to find new ToolMessages).
        last_ai_idx: int | None = None
        for i in range(len(messages) - 1, -1, -1):
            if isinstance(messages[i], AIMessage):
                last_ai_idx = i
                break

        # Re-apply step-1 to AIMessages (restore any deanonymized originals).
        for i, msg in enumerate(messages):
            if not isinstance(msg, AIMessage):
                continue
            updated = self._reapply_step1(msg)
            if updated is not msg:
                new_messages[i] = updated
                any_modified = True

        # Full anonymization for the last HumanMessage.
        for i in range(len(messages) - 1, -1, -1):
            if isinstance(messages[i], HumanMessage):
                updated = self._anonymize_message(messages[i])
                if updated is not messages[i]:
                    new_messages[i] = updated
                    any_modified = True
                break

        # Full anonymization for ToolMessages after the last AIMessage.
        if last_ai_idx is not None:
            for i in range(last_ai_idx + 1, len(messages)):
                if isinstance(messages[i], ToolMessage):
                    updated = self._anonymize_message(messages[i])
                    if updated is not messages[i]:
                        new_messages[i] = updated
                        any_modified = True

        # Collect mapping entries created during this call.
        new_to_token = {
            k: v for k, v in self._to_token.items() if k not in snapshot_to_token
        }
        new_to_original = {self._to_token[k]: k for k in new_to_token}

        result: dict[str, Any] = {}
        if any_modified:
            result["messages"] = new_messages
        if new_to_token:
            result["pii_to_token"] = new_to_token
            result["pii_to_original"] = new_to_original

        return result or None

    async def abefore_model(
        self,
        state: PIIState,
        runtime: Runtime,
    ) -> dict[str, Any] | None:
        """Async version of :meth:`before_model`.

        Args:
            state: Current agent state.
            runtime: LangGraph runtime.

        Returns:
            State patch or ``None``.
        """
        return self.before_model(state, runtime)

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command],
    ) -> ToolMessage | Command:
        """Deanonymize tool arguments before execution.

        The tool result is returned **raw** (not anonymized).  The next
        ``before_model`` call will anonymize it before the LLM sees it.

        Args:
            request: Tool call request with (potentially tokenized) arguments.
            handler: Callable that executes the tool.

        Returns:
            Raw ``ToolMessage`` from the tool, or a ``Command`` unchanged.
        """
        self._sync_from_state(request.state)

        deanonymized_args: dict[str, Any] = {
            k: self.deanonymize(v) if isinstance(v, str) else v
            for k, v in request.tool_call["args"].items()
        }
        deanonymized_tool_call: ToolCall = {  # type: ignore[typeddict-unknown-key]
            **request.tool_call,
            "args": deanonymized_args,
        }
        new_request = ToolCallRequest(
            tool_call=deanonymized_tool_call,
            tool=request.tool,
            state=request.state,
            runtime=request.runtime,
        )
        return handler(new_request)

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command]],
    ) -> ToolMessage | Command:
        """Async version of :meth:`wrap_tool_call`.

        Args:
            request: Tool call request.
            handler: Async callable that executes the tool.

        Returns:
            Raw ``ToolMessage`` from the tool, or a ``Command`` unchanged.
        """
        self._sync_from_state(request.state)

        deanonymized_args: dict[str, Any] = {
            k: self.deanonymize(v) if isinstance(v, str) else v
            for k, v in request.tool_call["args"].items()
        }
        deanonymized_tool_call: ToolCall = {  # type: ignore[typeddict-unknown-key]
            **request.tool_call,
            "args": deanonymized_args,
        }
        new_request = ToolCallRequest(
            tool_call=deanonymized_tool_call,
            tool=request.tool,
            state=request.state,
            runtime=request.runtime,
        )
        return await handler(new_request)

    def after_agent(
        self,
        state: PIIState,
        runtime: Runtime,
    ) -> dict[str, Any] | None:
        """Deanonymize the final assistant message so the user sees real values.

        Args:
            state: Agent state after the last LLM call.
            runtime: LangGraph runtime (unused).

        Returns:
            State patch with deanonymized last message, or ``None`` if nothing
            changed.
        """
        self._sync_from_state(state)

        messages = state.get("messages")
        if not messages:
            return None

        last = messages[-1]
        if not isinstance(last, AIMessage) or not isinstance(last.content, str):
            return None

        deanonymized = self.deanonymize(last.content)
        if deanonymized == last.content:
            return None

        return {
            "messages": [
                AIMessage(
                    content=deanonymized,
                    tool_calls=last.tool_calls if hasattr(last, "tool_calls") else [],
                    id=last.id,
                )
            ]
        }

    async def aafter_agent(
        self,
        state: PIIState,
        runtime: Runtime,
    ) -> dict[str, Any] | None:
        """Async version of :meth:`after_agent`.

        Args:
            state: Agent state after the last LLM call.
            runtime: LangGraph runtime.

        Returns:
            State patch or ``None``.
        """
        return self.after_agent(state, runtime)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _sync_from_state(self, state: Any) -> None:
        """Load the PII mapping from *state* into the instance cache.

        Args:
            state: Agent state dict that may contain ``pii_to_token`` and
                ``pii_to_original`` entries.
        """
        self._to_token = dict(state.get("pii_to_token") or {})
        self._to_original = dict(state.get("pii_to_original") or {})

    def _get_or_create_token(self, original: str, entity_type: str) -> str:
        """Return the deterministic token for *original*, creating it if needed.

        Args:
            original: The raw PII string (e.g. ``"Jean Dupont"``).
            entity_type: The entity category (e.g. ``"PERSON"``).

        Returns:
            A token of the form ``<ENTITY_TYPE:xxxxxxxx>``.
        """
        if original in self._to_token:
            return self._to_token[original]

        token = f"<{entity_type}:{_short_hash(original)}>"
        self._to_token[original] = token
        self._to_original[token] = original
        return token

    def _reapply_step1(self, message: AIMessage) -> AIMessage:
        """Replace known originals in *message* content without running GLiNER2.

        Used to re-anonymize AI messages that were deanonymized by
        :meth:`after_agent`.

        Args:
            message: The AI message to re-anonymize.

        Returns:
            Updated ``AIMessage`` if content changed, otherwise the original.
        """
        if not isinstance(message.content, str):
            return message

        new_content = message.content
        for original, token in self._to_token.items():
            new_content = new_content.replace(original, token)

        if new_content == message.content:
            return message

        return AIMessage(
            content=new_content,
            tool_calls=message.tool_calls if hasattr(message, "tool_calls") else [],
            id=message.id,
        )

    def _anonymize_message(self, message: Any) -> Any:
        """Return a copy of *message* with all PII anonymized via GLiNER2.

        ``AIMessage`` instances are handled by :meth:`_reapply_step1` instead.

        Args:
            message: A LangChain message object.

        Returns:
            New message with PII replaced, or the original if unchanged.
        """
        if isinstance(message, AIMessage):
            return message

        if not isinstance(message, (HumanMessage, SystemMessage, ToolMessage)):
            return message

        if isinstance(message.content, str):
            new_content: Any = self.anonymize(message.content)
        elif isinstance(message.content, list):
            new_content = [
                {**block, "text": self.anonymize(block["text"])}
                if isinstance(block, dict) and "text" in block
                else block
                for block in message.content
            ]
        else:
            return message

        kwargs: dict[str, Any] = {"content": new_content}

        if hasattr(message, "tool_calls") and message.tool_calls:
            kwargs["tool_calls"] = [
                {
                    **tc,
                    "args": {
                        k: self.anonymize(v) if isinstance(v, str) else v
                        for k, v in tc["args"].items()
                    },
                }
                for tc in message.tool_calls
            ]
        if hasattr(message, "tool_call_id") and message.tool_call_id:
            kwargs["tool_call_id"] = message.tool_call_id
        if hasattr(message, "name") and message.name:
            kwargs["name"] = message.name
        if hasattr(message, "id") and message.id:
            kwargs["id"] = message.id

        return type(message)(**kwargs)
