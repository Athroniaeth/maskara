"""Langfuse-backed implementation of the observation service.

The Langfuse v3 SDK already exposes ``start_as_current_observation``
on both the ``Langfuse`` client and on each ``LangfuseSpan`` returned
by it, with the exact kwargs we need (``name``, ``as_type``, ``input``,
``output``). ``LangfuseObservationService`` and ``LangfuseSpan`` are
therefore thin adapters: each method forwards to the wrapped object.
"""

from __future__ import annotations

import importlib.util
from contextlib import contextmanager
from typing import Any

if importlib.util.find_spec("langfuse") is None:
    raise ImportError(
        "You must install langfuse to use LangfuseObservationService, "
        "please install piighost[langfuse]"
    )

from langfuse import Langfuse

from piighost.observation.base import (
    AbstractObservationService,
    AbstractSpan,
)


class LangfuseSpan(AbstractSpan):
    """``AbstractSpan`` backed by a live Langfuse observation.

    Holds a reference to the wrapped Langfuse object and forwards all
    methods to it. Nested observations created via
    ``start_as_current_observation`` re-enter the same wrapper so the
    contract is honoured at every depth.
    """

    def __init__(self, lf_span: Any) -> None:
        self._lf_span = lf_span

    @contextmanager
    def start_as_current_observation(
        self,
        *,
        name: str,
        as_type: str = "span",
        input: Any = None,
        output: Any = None,
    ):
        kwargs: dict[str, Any] = {"name": name, "as_type": as_type}
        if input is not None:
            kwargs["input"] = input
        if output is not None:
            kwargs["output"] = output
        with self._lf_span.start_as_current_observation(**kwargs) as nested:
            yield LangfuseSpan(nested)

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
            self._lf_span.update(**kwargs)

    def update_trace(
        self,
        *,
        user_id: str | None = None,
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        tags: list[str] | None = None,
    ) -> None:
        kwargs: dict[str, Any] = {}
        if user_id is not None:
            kwargs["user_id"] = user_id
        if session_id is not None:
            kwargs["session_id"] = session_id
        if metadata is not None:
            kwargs["metadata"] = metadata
        if tags is not None:
            kwargs["tags"] = tags
        if kwargs:
            self._lf_span.update_trace(**kwargs)


class LangfuseObservationService(AbstractObservationService):
    """``AbstractObservationService`` that produces ``LangfuseSpan`` instances.

    Wraps a ``Langfuse`` client and forwards ``start_as_current_span``
    to ``client.start_as_current_observation(as_type="span", ...)``.
    """

    def __init__(self, client: Langfuse) -> None:
        self._client = client

    @contextmanager
    def start_as_current_span(
        self,
        *,
        name: str,
        input: Any = None,
        output: Any = None,
    ):
        kwargs: dict[str, Any] = {"name": name, "as_type": "span"}
        if input is not None:
            kwargs["input"] = input
        if output is not None:
            kwargs["output"] = output
        with self._client.start_as_current_observation(**kwargs) as obs:
            yield LangfuseSpan(obs)

    def flush(self) -> None:
        self._client.flush()
