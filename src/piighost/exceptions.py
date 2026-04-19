"""PIIGhost exception hierarchy."""


class PIIGhostException(Exception):
    """Base exception for all PIIGhost errors."""


class CacheMissError(PIIGhostException):
    """Raised when a cache lookup finds no entry for the given key."""


class DeanonymizationError(PIIGhostException):
    """Raised when a token cannot be found during deanonymization."""

    def __init__(self, message: str, partial_text: str) -> None:
        super().__init__(message)
        self.partial_text = partial_text


class RehydrationError(DeanonymizationError):
    """Raised when a document's anonymization mapping is missing or malformed.

    Subclass of DeanonymizationError because rehydration is semantically
    a deanonymization step, just driven from Document.meta rather than
    from the pipeline cache.
    """
