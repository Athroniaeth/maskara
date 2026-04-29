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

from langfuse import Langfuse, propagate_attributes

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
        # Langfuse v4 dropped the per-span ``update_trace`` API. Trace-
        # level attributes are now set via ``propagate_attributes``
        # which has to bracket the trace (see
        # ``LangfuseObservationService.start_as_current_span``). Calling
        # ``update_trace`` mid-stream is therefore a no-op for the
        # Langfuse backend; pass these fields when creating the root
        # span instead.
        return None


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
        session_id: str | None = None,
        user_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        tags: list[str] | None = None,
    ):
        obs_kwargs: dict[str, Any] = {"name": name, "as_type": "span"}
        if input is not None:
            obs_kwargs["input"] = input
        if output is not None:
            obs_kwargs["output"] = output

        prop_kwargs: dict[str, Any] = {}
        if session_id is not None:
            prop_kwargs["session_id"] = session_id
        if user_id is not None:
            prop_kwargs["user_id"] = user_id
        if metadata is not None:
            # Langfuse propagate_attributes only accepts string values.
            # Coerce non-string scalars so the call does not raise.
            prop_kwargs["metadata"] = {
                k: v if isinstance(v, str) else str(v) for k, v in metadata.items()
            }
        if tags is not None:
            prop_kwargs["tags"] = tags

        with self._client.start_as_current_observation(**obs_kwargs) as obs:
            if prop_kwargs:
                with propagate_attributes(**prop_kwargs):
                    yield LangfuseSpan(obs)
            else:
                yield LangfuseSpan(obs)

    def flush(self) -> None:
        self._client.flush()
