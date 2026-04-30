"""Opik-backed implementation of the observation service.

The Opik SDK exposes ``opik.start_as_current_trace`` and
``opik.start_as_current_span`` as context managers that yield mutable
``TraceData`` / ``SpanData`` records. Mutating those records via
``.update(input=..., output=...)`` updates what the SDK exports when
the context closes, which is the mechanism ``OpikSpan.update`` rides
on. ``OpikObservationService`` and ``OpikSpan`` are therefore thin
adapters: each method forwards to the Opik primitive whose vocabulary
matches.
"""

from __future__ import annotations

import importlib.util
from contextlib import contextmanager
from typing import Any

if importlib.util.find_spec("opik") is None:
    raise ImportError(
        "You must install opik to use OpikObservationService, "
        "please install piighost[opik]"
    )

import opik
from opik import Opik

from piighost.observation.base import (
    AbstractObservationService,
    AbstractSpan,
)


# Map our backend-agnostic ``as_type`` (Langfuse vocabulary) to Opik's
# narrower ``type`` literal. Opik has no dedicated ``event`` kind so
# we collapse onto ``general``; ``generation`` maps to ``llm`` which
# is Opik's term for model calls.
_AS_TYPE_TO_OPIK: dict[str, str] = {
    "span": "general",
    "tool": "tool",
    "guardrail": "guardrail",
    "generation": "llm",
    "event": "general",
}


class OpikSpan(AbstractSpan):
    """``AbstractSpan`` backed by an Opik ``SpanData`` or ``TraceData``.

    Holds a reference to the data record yielded by the Opik context
    manager. ``update`` mutates that record so the SDK export at
    context-exit carries the new values. Nested observations open a
    child Opik span under whichever Opik span is currently active in
    the calling thread, mirroring the Langfuse adapter.
    """

    def __init__(self, data: Any) -> None:
        self._data = data

    @contextmanager
    def start_as_current_observation(
        self,
        *,
        name: str,
        as_type: str = "span",
        input: Any = None,
        output: Any = None,
    ):
        kwargs: dict[str, Any] = {
            "name": name,
            "type": _AS_TYPE_TO_OPIK.get(as_type, "general"),
        }
        if input is not None:
            kwargs["input"] = input
        if output is not None:
            kwargs["output"] = output
        with opik.start_as_current_span(**kwargs) as nested:
            yield OpikSpan(nested)

    def update(
        self,
        *,
        input: Any = None,
        output: Any = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        kwargs: dict[str, Any] = {}
        if input is not None:
            kwargs["input"] = input
        if output is not None:
            kwargs["output"] = output
        if metadata is not None:
            kwargs["metadata"] = metadata
        if kwargs:
            self._data.update(**kwargs)

    def update_trace(
        self,
        *,
        user_id: str | None = None,
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        tags: list[str] | None = None,
    ) -> None:
        # Trace-level fields are passed at trace creation time via
        # ``OpikObservationService.start_as_current_span``. Mirror the
        # Langfuse adapter's no-op for spans created later in the
        # trace lifetime; pass these fields when opening the root span
        # instead.
        return None


class OpikObservationService(AbstractObservationService):
    """``AbstractObservationService`` that produces ``OpikSpan`` instances.

    Wraps an :class:`Opik` client and forwards
    ``start_as_current_span`` to ``opik.start_as_current_trace``. The
    backend-agnostic ``session_id`` is mapped onto Opik's
    ``thread_id`` (Opik's name for conversation-grouping). ``user_id``
    is folded into ``metadata`` (Opik has no first-class user field on
    a trace). ``tags`` are forwarded as-is.

    The constructor calls :func:`opik.set_global_client` so the
    module-level ``start_as_current_*`` helpers route to the same
    backend instance. Pass ``None`` to rely on whatever global client
    is already configured (for example via env vars and
    ``opik.configure``).
    """

    def __init__(self, client: Opik | None = None) -> None:
        if client is not None:
            opik.set_global_client(client)
            self._client: Opik = client
        else:
            self._client = opik.get_global_client()

    @contextmanager
    def start_as_current_span(
        self,
        *,
        name: str,
        input: Any = None,
        output: Any = None,
        session_id: str | None = None,
        user_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        tags: list[str] | None = None,
    ):
        kwargs: dict[str, Any] = {"name": name}
        if input is not None:
            kwargs["input"] = input
        if output is not None:
            kwargs["output"] = output
        if session_id is not None:
            kwargs["thread_id"] = session_id
        if tags is not None:
            kwargs["tags"] = tags

        merged_metadata: dict[str, Any] = dict(metadata) if metadata else {}
        if user_id is not None:
            merged_metadata["user_id"] = user_id
        if merged_metadata:
            kwargs["metadata"] = merged_metadata

        with opik.start_as_current_trace(**kwargs) as trace_data:
            yield OpikSpan(trace_data)

    def flush(self) -> None:
        self._client.flush()
