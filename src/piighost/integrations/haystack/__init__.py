"""Haystack integration for PIIGhost.

Install with: uv add piighost[haystack]
"""

import importlib.util

if importlib.util.find_spec("haystack") is None:
    raise ImportError(
        "You must install haystack to use the Haystack integration, "
        "please install piighost[haystack]"
    )

from piighost.integrations.haystack.documents import (
    PIIGhostDocumentAnonymizer,
    PIIGhostDocumentClassifier,
    PIIGhostQueryAnonymizer,
    PIIGhostRehydrator,
)
from piighost.integrations.haystack.lancedb import lancedb_meta_fields
from piighost.integrations.haystack.presets import (
    PRESET_GDPR,
    PRESET_LANGUAGE,
    PRESET_SENSITIVITY,
)
from piighost.integrations.haystack.rag import PIIGhostRetriever  # noqa: F401

__all__ = [
    "PIIGhostDocumentAnonymizer",
    "PIIGhostDocumentClassifier",
    "PIIGhostQueryAnonymizer",
    "PIIGhostRehydrator",
    "PRESET_GDPR",
    "PRESET_LANGUAGE",
    "PRESET_SENSITIVITY",
    "lancedb_meta_fields",
    "PIIGhostRetriever",
]
