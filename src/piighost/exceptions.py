"""PIIGhost exception and warning hierarchy."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from piighost.models import Detection


class PIIGhostException(Exception):
    """Base exception for all PIIGhost errors."""


class CacheMissError(PIIGhostException):
    """Raised when a cache lookup finds no entry for the given key."""


class DeanonymizationError(PIIGhostException):
    """Raised when a token cannot be found during deanonymization."""

    def __init__(self, message: str, partial_text: str) -> None:
        super().__init__(message)
        self.partial_text = partial_text


class PIIRemainingError(PIIGhostException):
    """Raised by an ``AnyGuardRail`` when the anonymized text still
    contains detections.

    Carries the residual detections produced by the guard's detector so
    callers can log them, surface them in an error response, or feed
    them into a fallback policy.
    """

    detections: list[Detection]

    def __init__(self, message: str, detections: list[Detection]) -> None:
        super().__init__(message)
        self.detections = detections


class PIIGhostConfigWarning(UserWarning):
    """Emitted when a pipeline configuration is likely to cause silent
    correctness issues at runtime (e.g. an in-memory cache used across
    multiple workers).

    Filterable via ``warnings.filterwarnings("ignore",
    category=PIIGhostConfigWarning)``.
    """
