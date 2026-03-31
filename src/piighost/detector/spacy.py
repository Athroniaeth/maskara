import importlib.util

from piighost.models import Detection, Span

if importlib.util.find_spec("spacy") is None:
    raise ImportError(
        "You must install spacy to use SpacyDetector, please install piighost[spacy]"
    )

import spacy


class SpacyDetector:
    """Detect entities using a spaCy NER model.

    Wraps a loaded spaCy ``Language`` model so that callers can inject a
    pre-loaded model (useful for tests and shared workers).

    Args:
        model: A loaded spaCy ``Language`` model instance.
        labels: Entity types to keep (``None`` keeps all).

    Example:
        >>> import spacy
        >>> nlp = spacy.load("fr_core_news_sm")
        >>> detector = SpacyDetector(model=nlp, labels=["PER", "LOC"])
        >>> detections = await detector.detect("Patrick habite à Paris")
    """

    def __init__(
        self,
        model: spacy.language.Language,
        labels: list[str] | None = None,
    ) -> None:
        self.model = model
        self.labels = labels

    async def detect(self, text: str) -> list[Detection]:
        """Run spaCy NER and convert results to ``Detection`` objects.

        Args:
            text: The input text to search for entities.

        Returns:
            Detections for each entity found by the model.
        """
        doc = self.model(text)
        return [
            Detection(
                text=ent.text,
                label=ent.label_,
                position=Span(start_pos=ent.start_char, end_pos=ent.end_char),
                confidence=1.0,
            )
            for ent in doc.ents
            if self.labels is None or ent.label_ in self.labels
        ]
