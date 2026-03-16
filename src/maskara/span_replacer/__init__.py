"""Span-based text replacement with reversible mappings."""

from span_replacer.models import Span, ReplacementResult
from span_replacer.validator import SpanValidator, DefaultSpanValidator
from span_replacer.replacer import SpanReplacer

__all__ = [
    "Span",
    "ReplacementResult",
    "SpanValidator",
    "DefaultSpanValidator",
    "SpanReplacer",
]
