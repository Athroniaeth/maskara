"""Span-based text replacement with reversible mappings."""

from piighost.span_replacer.models import Span, ReplacementResult
from piighost.span_replacer.validator import SpanValidator, DefaultSpanValidator
from piighost.span_replacer.replacer import SpanReplacer

__all__ = [
    "Span",
    "ReplacementResult",
    "SpanValidator",
    "DefaultSpanValidator",
    "SpanReplacer",
]
