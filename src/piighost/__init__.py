"""PIIGhost - PII anonymization for text and AI agent conversations."""

# ---- Tier 1: Core (synchronous text processing) ----

from piighost.anonymizer import (
    Anonymizer,
    AnonymizationResult,
    CompositeDetector,
    CounterPlaceholderFactory,
    Entity,
    EntityDetector,
    GlinerDetector,
    HashPlaceholderFactory,
    IrreversibleAnonymizationError,
    IrreversiblePlaceholderFactory,
    OccurrenceFinder,
    Placeholder,
    PlaceholderFactory,
    RedactPlaceholderFactory,
    RegexDetector,
    RegexOccurrenceFinder,
    ReversiblePlaceholderFactory,
)
from piighost.span_replacer import (
    DefaultSpanValidator,
    ReplacementResult,
    Span,
    SpanReplacer,
    SpanValidator,
)

# ---- Tier 2: Session (stateful registry + async caching) ----

from piighost.pipeline import (
    AnonymizationPipeline,
    InMemoryPlaceholderStore,
    PlaceholderStore,
)
from piighost.registry import PlaceholderRegistry

# ---- Tier 3: Integration (LangChain/LangGraph) ----
# NOT re-exported here — importing middleware.py triggers an ImportError
# when langchain is not installed, which would break `import piighost`.
# Users must import explicitly:
#   from piighost.middleware import PIIAnonymizationMiddleware

__all__ = [
    # Core
    "Anonymizer",
    "AnonymizationResult",
    "CompositeDetector",
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
    "RegexDetector",
    "RegexOccurrenceFinder",
    "ReversiblePlaceholderFactory",
    "DefaultSpanValidator",
    "ReplacementResult",
    "Span",
    "SpanReplacer",
    "SpanValidator",
    # Session
    "AnonymizationPipeline",
    "InMemoryPlaceholderStore",
    "PlaceholderRegistry",
    "PlaceholderStore",
]
