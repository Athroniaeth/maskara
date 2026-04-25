---
icon: lucide/play
---

# Premier pipeline

L'usage le plus simple : créer un `AnonymizationPipeline` et l'appeler directement sur du texte.

```python
import asyncio

from gliner2 import GLiNER2

from piighost.anonymizer import Anonymizer
from piighost.detector import Gliner2Detector
from piighost.linker.entity import ExactEntityLinker
from piighost.entity_resolver import MergeEntityConflictResolver
from piighost.pipeline import AnonymizationPipeline
from piighost.placeholder import LabelCounterPlaceholderFactory
from piighost.span_resolver import ConfidenceSpanConflictResolver

# 1. Charger le modèle NER
model = GLiNER2.from_pretrained("fastino/gliner2-multi-v1")

# 2. Instancier chaque composant
detector = Gliner2Detector(model=model, labels=["PERSON", "LOCATION"], threshold=0.5)
span_resolver = ConfidenceSpanConflictResolver()
entity_linker = ExactEntityLinker()
entity_resolver = MergeEntityConflictResolver()
anonymizer = Anonymizer(LabelCounterPlaceholderFactory())

# 3. Assembler le pipeline
pipeline = AnonymizationPipeline(
    detector=detector,
    span_resolver=span_resolver,
    entity_linker=entity_linker,
    entity_resolver=entity_resolver,
    anonymizer=anonymizer,
)


async def main():
    # 4. Anonymiser
    anonymized, entities = await pipeline.anonymize(
        "Patrick habite à Paris. Patrick aime Paris.",
    )
    print(anonymized)
    # <<PERSON:1>> habite à <<LOCATION:1>>. <<PERSON:1>> aime <<LOCATION:1>>.

    # 5. Désanonymiser
    original, _ = await pipeline.deanonymize(anonymized)
    print(original)
    # Patrick habite à Paris. Patrick aime Paris.


asyncio.run(main())
```

!!! info "Labels disponibles"
    Les labels supportés dépendent du modèle NER utilisé. Les labels courants incluent `"PERSON"`, `"LOCATION"`, `"ORGANIZATION"`, `"EMAIL"`, `"PHONE"`.

Pour enchaîner plusieurs messages dans une conversation avec mémoire partagée, voir [Pipeline conversationnel](conversation.md).
