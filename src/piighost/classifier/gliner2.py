"""GLiNER2-backed classifier. Gated on the ``gliner2`` extra."""

import importlib.util

from piighost.classifier.base import ClassificationSchema

if importlib.util.find_spec("gliner2") is None:
    raise ImportError(
        "You must install gliner2 to use Gliner2Classifier, "
        "please install piighost[gliner2]"
    )

from gliner2 import GLiNER2


class Gliner2Classifier:
    """Classify text against named schemas using a GLiNER2 model.

    Reuses an already-loaded ``GLiNER2`` instance so the same model
    can power both NER (via ``Gliner2Detector``) and classification.

    Args:
        model: A loaded ``GLiNER2`` model instance.

    Example:
        >>> from gliner2 import GLiNER2
        >>> model = GLiNER2.from_pretrained("fastino/gliner2-multi-v1")
        >>> classifier = Gliner2Classifier(model=model)
    """

    model: GLiNER2

    def __init__(self, model: GLiNER2) -> None:
        self.model = model

    async def classify(
        self,
        text: str,
        schemas: dict[str, ClassificationSchema],
    ) -> dict[str, list[str]]:
        """Run ``model.classify_text`` and return a label dict per axis.

        Args:
            text: Input text to classify.
            schemas: Named classification axes.

        Returns:
            A dict mapping each axis name to the list of picked labels.
        """
        if not schemas:
            return {}
        raw = self.model.classify_text(text, schemas)
        return {
            name: list(raw.get(name, [])) if raw.get(name) else [] for name in schemas
        }
