"""Anonymization pipeline: detect, expand, replace, deanonymize."""

from piighost.anonymizer.anonymizer import Anonymizer
from piighost.anonymizer.detector import EntityDetector, GlinerDetector
from piighost.anonymizer.models import (
    AnonymizationResult,
    Entity,
    IrreversibleAnonymizationError,
    Placeholder,
)
from piighost.anonymizer.occurrence import OccurrenceFinder, RegexOccurrenceFinder
from piighost.anonymizer.placeholder import (
    CounterPlaceholderFactory,
    HashPlaceholderFactory,
    IrreversiblePlaceholderFactory,
    PlaceholderFactory,
    RedactPlaceholderFactory,
    ReversiblePlaceholderFactory,
)

__all__ = [
    "Anonymizer",
    "AnonymizationResult",
    "CounterPlaceholderFactory",
    "Entity",
    "EntityDetector",
    "GlinerDetector",
    "HashPlaceholderFactory",
    "IrreversibleAnonymizationError",
    "IrreversiblePlaceholderFactory",
    "OccurrenceFinder",
    "Placeholder",
    "PlaceholderFactory",
    "RedactPlaceholderFactory",
    "ReversiblePlaceholderFactory",
    "RegexOccurrenceFinder",
]
