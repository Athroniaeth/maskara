"""PIIGhost exception hierarchy."""


class PIIGhostException(Exception):
    """Base exception for all PIIGhost errors."""


class CacheMissError(PIIGhostException):
    """Raised when a cache lookup finds no entry for the given key."""