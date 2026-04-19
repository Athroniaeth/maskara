"""Base classifier protocol and schema types."""

from typing import Protocol, TypedDict


class ClassificationSchema(TypedDict, total=False):
    """Schema describing a single classification axis.

    Fields match the GLiNER2 ``classify_text`` API so that implementations
    can pass them through directly.

    Attributes:
        labels: Candidate label values for this axis (e.g. ``["en", "fr"]``).
        multi_label: If ``True``, multiple labels may be returned.
            Defaults to ``False`` (single-label).
        cls_threshold: Minimum confidence for a label to be picked.
            Defaults to the implementation's own choice (e.g. 0.5).
    """

    labels: list[str]
    multi_label: bool
    cls_threshold: float


class AnyClassifier(Protocol):
    """Protocol for text classification components.

    Implementations take a text and a dict of named classification
    axes (``schemas``) and return a dict mapping each axis name to
    the list of picked labels.
    """

    async def classify(
        self,
        text: str,
        schemas: dict[str, ClassificationSchema],
    ) -> dict[str, list[str]]:
        """Classify ``text`` against each axis in ``schemas``.

        Args:
            text: The input text to classify.
            schemas: Named classification axes.

        Returns:
            A dict with the same keys as ``schemas``, each mapped to the
            list of labels picked for that axis.
        """
        ...
