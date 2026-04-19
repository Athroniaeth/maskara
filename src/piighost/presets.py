"""Ready-made classification schemas for common compliance use cases.

Framework-agnostic: consumed by every integration that exposes a
classifier component (Haystack, LangChain, future adapters). Edit here
only; integration subpackages re-export for import-path compatibility.
"""

from piighost.classifier.base import ClassificationSchema

PRESET_GDPR: dict[str, ClassificationSchema] = {
    "gdpr_category": {
        "labels": [
            "health",
            "financial",
            "biometric",
            "political",
            "children",
            "none",
        ],
        "multi_label": True,
    },
}

PRESET_SENSITIVITY: dict[str, ClassificationSchema] = {
    "sensitivity": {
        "labels": ["low", "medium", "high"],
        "multi_label": False,
    },
}

PRESET_LANGUAGE: dict[str, ClassificationSchema] = {
    "language": {
        "labels": ["fr", "en", "de", "es", "it", "nl"],
        "multi_label": False,
    },
}

__all__ = ["PRESET_GDPR", "PRESET_LANGUAGE", "PRESET_SENSITIVITY"]
