"""Observation services for piighost pipelines.

Pipelines can be instrumented with an observation service so each
anonymisation run produces a structured trace of detect / link /
placeholder / guard stages with input and output recorded for each.

The interface is deliberately a tiny mirror of the Langfuse v3 SDK
(``start_as_current_span`` on the service, ``start_as_current_observation``
+ ``update`` + ``update_trace`` on each span). Backends are added by
subclassing ``AbstractObservationService`` and ``AbstractSpan``.
"""

from piighost.observation.base import (
    AbstractObservationService,
    AbstractSpan,
    NoOpObservationService,
    NoOpSpan,
)

__all__ = [
    "AbstractObservationService",
    "AbstractSpan",
    "NoOpObservationService",
    "NoOpSpan",
]
