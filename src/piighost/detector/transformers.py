import importlib.util

from piighost.detector.base import BaseNERDetector
from piighost.models import Detection, Span

if importlib.util.find_spec("transformers") is None:
    raise ImportError(
        "You must install transformers to use TransformersDetector, "
        "please install piighost[transformers]"
    )

from transformers.pipelines.token_classification import TokenClassificationPipeline


class TransformersDetector(BaseNERDetector):
    """Detect entities using a Hugging Face token-classification pipeline.

    Wraps a loaded ``TokenClassificationPipeline`` so that callers can
    inject a pre-built pipeline (useful for tests and shared workers).

    Args:
        pipeline: A loaded HF ``TokenClassificationPipeline``.
        labels: Entity types to keep. ``None`` or ``[]`` keeps every
            entity (no filtering, label is passed through). A list
            performs identity mapping and filters by those labels.
            A ``{external: internal}`` dict filters by internal labels
            and rewrites :class:`Detection.label` to the corresponding
            external.

    Example:
        >>> from transformers import pipeline
        >>> ner = pipeline("ner", model="dslim/bert-base-NER", aggregation_strategy="simple")
        >>> detector = TransformersDetector(pipeline=ner, labels=["PER", "LOC"])
        >>> # Remap model-native labels to stable external labels:
        >>> detector = TransformersDetector(
        ...     pipeline=ner,
        ...     labels={"PERSON": "PER", "LOCATION": "LOC"},
        ... )
        >>> detections = await detector.detect("Patrick lives in Paris")
    """

    def __init__(
        self,
        pipeline: TokenClassificationPipeline,
        labels: list[str] | dict[str, str] | None = None,
    ) -> None:
        super().__init__(labels)
        self.pipeline = pipeline

    async def detect(self, text: str) -> list[Detection]:
        """Run HF token-classification and convert results to ``Detection`` objects.

        Args:
            text: The input text to search for entities.

        Returns:
            Detections for each entity found by the model. When the label
            map is empty, every entity is kept with its raw model label.
            Otherwise only entities whose raw label is a mapped internal
            label are kept, and the external label is used in
            :class:`Detection.label`.
        """
        results = self.pipeline(text)
        detections: list[Detection] = []

        for ent in results:
            raw_label = ent.get("entity_group", ent.get("entity", "UNKNOWN"))

            if not self._label_map:
                label = raw_label
            else:
                mapped = self._map_label(raw_label)
                if mapped is None:
                    continue
                label = mapped

            start = int(ent["start"])
            end = int(ent["end"])
            detections.append(
                Detection(
                    text=text[start:end],
                    label=label,
                    position=Span(start_pos=start, end_pos=end),
                    confidence=float(ent["score"]),
                )
            )

        return detections
