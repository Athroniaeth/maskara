"""Abstract base classes for piighost observation services.

The interface mirrors the Langfuse v3 SDK so any developer who has
used Langfuse can read piighost telemetry code with no extra context.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import AbstractContextManager, contextmanager
from typing import Any


class AbstractSpan(ABC):
    """Handle to one observation in a trace.

    Mirrors the relevant subset of the Langfuse v3 ``LangfuseSpan`` API
    (``start_as_current_observation``, ``update``, ``update_trace``)
    so that pipeline code reads the same regardless of the concrete
    backend in use.
    """

    @abstractmethod
    def start_as_current_observation(
        self,
        *,
        name: str,
        as_type: str = "span",
        input: Any = None,
        output: Any = None,
    ) -> AbstractContextManager["AbstractSpan"]:
        """Open a child observation and yield its handle.

        ``as_type`` follows the Langfuse vocabulary
        (``"span"`` / ``"tool"`` / ``"event"`` / ``"generation"``).
        """
        raise NotImplementedError

    @abstractmethod
    def update(
        self,
        *,
        input: Any = None,
        output: Any = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Attach or replace data on this observation."""
        raise NotImplementedError

    @abstractmethod
    def update_trace(
        self,
        *,
        user_id: str | None = None,
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        tags: list[str] | None = None,
    ) -> None:
        """Update fields on the parent trace this observation belongs to."""
        raise NotImplementedError


class AbstractObservationService(ABC):
    """Backend-agnostic factory for observation root spans.

    Implementations wrap a backend client (Langfuse, Phoenix, Opik…)
    and produce :class:`AbstractSpan` instances when ``start_as_current_span``
    is called.
    """

    @abstractmethod
    def start_as_current_span(
        self,
        *,
        name: str,
        input: Any = None,
        output: Any = None,
    ) -> AbstractContextManager[AbstractSpan]:
        """Open a root span and yield its handle."""
        raise NotImplementedError

    def flush(self) -> None:
        """Flush any pending data to the backend.

        The default does nothing. Override when the backend buffers
        observations.
        """
        return None


class NoOpSpan(AbstractSpan):
    """Span implementation that records nothing.

    Used by :class:`NoOpObservationService` (the default when no
    backend is configured) and as a stand-in inside the pipeline when
    a stage runs without an active observation.
    """

    @contextmanager
    def start_as_current_observation(
        self,
        *,
        name: str,
        as_type: str = "span",
        input: Any = None,
        output: Any = None,
    ):
        yield self

    def update(
        self,
        *,
        input: Any = None,
        output: Any = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        return None

    def update_trace(
        self,
        *,
        user_id: str | None = None,
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        tags: list[str] | None = None,
    ) -> None:
        return None


class NoOpObservationService(AbstractObservationService):
    """Observation service that records nothing.

    Returned by ``pipeline._observation`` when the user instantiated
    the pipeline without an explicit ``observation`` argument, so that
    the pipeline can always call ``start_as_current_span`` without a
    None check.
    """

    @contextmanager
    def start_as_current_span(
        self,
        *,
        name: str,
        input: Any = None,
        output: Any = None,
    ):
        yield NoOpSpan()
