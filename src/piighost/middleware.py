"""Backwards-compatible re-export.

New code should import from ``piighost.integrations.langchain.middleware``.
"""

from piighost.integrations.langchain.middleware import (
    PIIAnonymizationMiddleware,
)

__all__ = ["PIIAnonymizationMiddleware"]
