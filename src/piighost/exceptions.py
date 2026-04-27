"""PIIGhost exception and warning hierarchy."""


class PIIGhostException(Exception):
    """Base exception for all PIIGhost errors."""


class CacheMissError(PIIGhostException):
    """Raised when a cache lookup finds no entry for the given key."""


class DeanonymizationError(PIIGhostException):
    """Raised when a token cannot be found during deanonymization."""

    def __init__(self, message: str, partial_text: str) -> None:
        super().__init__(message)
        self.partial_text = partial_text


class PIIGhostConfigWarning(UserWarning):
    """Emitted when a pipeline configuration is likely to cause silent
    correctness issues at runtime (e.g. an in-memory cache used across
    multiple workers).

    Filterable via ``warnings.filterwarnings("ignore",
    category=PIIGhostConfigWarning)``.
    """
