"""Test-double classifier that returns pre-configured results."""

from piighost.classifier.base import ClassificationSchema


class ExactMatchClassifier:
    """Classifier that returns hard-coded results per text.

    Useful for tests: configure with a ``{text: {schema: [labels]}}``
    mapping and it will return those labels when asked. Texts not in
    the mapping return empty label lists per schema.

    Args:
        results: Mapping from input text to expected classification output.

    Example:
        >>> classifier = ExactMatchClassifier(
        ...     results={"hello": {"sentiment": ["positive"]}}
        ... )
    """

    def __init__(self, results: dict[str, dict[str, list[str]]] | None = None) -> None:
        self._results = results or {}

    async def classify(
        self,
        text: str,
        schemas: dict[str, ClassificationSchema],
    ) -> dict[str, list[str]]:
        """Return configured labels for ``text``, or empty lists if unknown."""
        configured = self._results.get(text, {})
        return {name: configured.get(name, []) for name in schemas}
