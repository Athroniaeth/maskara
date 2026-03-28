import importlib.util

from piighost.models import Detection, Span

if importlib.util.find_spec("gliner2") is None:
    raise ImportError(
        "You must install gliner2 to use Gliner2Detector, please install piighost[gliner2] for use middleware"
    )

from gliner2 import GLiNER2


class Gliner2Detector:
    """Detect entities using a GLiNER2 model.

    Wraps a ``GLiNER2`` model instance so that callers can inject a
    pre-loaded model (useful for tests and shared workers).

    Args:
        model: A loaded ``GLiNER2`` model instance.
        labels: Entity types this detector is configured to find.
        threshold: Minimum confidence score to keep a prediction.
        flat_ner: Whether to use flat NER mode (no nested entities).

    Example:
        >>> from gliner2 import GLiNER2
        >>> model = GLiNER2.from_pretrained("urchade/gliner_multi_pii-v1")
        >>> detector = Gliner2Detector(model=model, labels=["PERSON", "LOCATION"])
        >>> detections = await detector.detect("Je m'appelle Patrick")
    """

    def __init__(
        self,
        model: GLiNER2,
        labels: list[str],
        threshold: float = 0.5,
        flat_ner: bool = True,
    ) -> None:
        self.model = model
        self.labels = labels
        self.threshold = threshold
        self.flat_ner = flat_ner

    async def detect(self, text: str) -> list[Detection]:
        """Run GLiNER2 prediction and convert results to ``Detection`` objects.

        Args:
            text: The input text to search for entities.

        Returns:
            Detections whose score meets the configured threshold.
        """
        raw_entities = self.model.extract_entities(
            text,
            entity_types=self.labels,
            threshold=self.threshold,
            include_spans=True,
            include_confidence=True,
        )["entities"]

        return [
            Detection(
                text=entity["text"],
                label=entity_type,
                position=Span(
                    start_pos=entity["start"],
                    end_pos=entity["end"],
                ),
                confidence=entity["confidence"],
            )
            for entity_type, list_entity in raw_entities.items()
            for entity in list_entity
        ]
