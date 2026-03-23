"""Immutable data models for the anonymization pipeline."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Entity:
    """A named entity detected by a NER model.

    Attributes:
        text: The surface form found in the source string.
        label: The entity type (e.g. ``"PERSON"``, ``"LOCATION"``).
        start: Inclusive start index in the source text.
        end: Exclusive end index in the source text.
        score: Confidence score returned by the model (0.0 – 1.0).
    """

    text: str
    label: str
    start: int
    end: int
    score: float


@dataclass(frozen=True)
class Placeholder:
    """Links a unique original fragment to its anonymised replacement.

    A placeholder groups every occurrence of the *same* sensitive text
    under one label and one replacement tag so that all occurrences are
    anonymised consistently.

    Attributes:
        original: The original sensitive text (e.g. ``"Patrick"``).
        label: The entity type (e.g. ``"PERSON"``).
        replacement: The placeholder tag (e.g. ``"<<PERSON_1>>"``).
    """

    original: str
    label: str
    replacement: str


@dataclass(frozen=True)
class AnonymizationResult:
    """Full output of an anonymization pass.

    Attributes:
        original_text: The input text before anonymization.
        anonymized_text: The text with all sensitive fragments replaced.
        placeholders: Every placeholder created during the pass.
        reverse_spans: Spans that undo the anonymization (delegated from
            the underlying ``ReplacementResult``).
    """

    original_text: str
    anonymized_text: str
    placeholders: tuple[Placeholder, ...]
    reverse_spans: tuple  # tuple[Span, ...] – avoids circular import


class IrreversibleAnonymizationError(Exception):
    """Raised when attempting to deanonymize a non-reversible anonymization.

    Some placeholder factories (e.g. ``RedactPlaceholderFactory``) produce
    identical replacement tags for every entity, making it impossible to
    map a tag back to its original value.
    """
    ...
