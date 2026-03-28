---
icon: lucide/shield
---

# PIIGhost

**Anonymisation transparente des donnees personnelles pour agents LLM.**

`piighost` est une bibliotheque Python qui detecte, anonymise et desanonymise automatiquement les entites sensibles (noms, lieux, etc.) dans les conversations d'agents IA. Elle s'integre via un middleware LangChain sans modifier votre code d'agent existant.

---

## Fonctionnalites

- **Pipeline 5 etapes** : Detect → Resolve Spans → Link Entities → Resolve Entities → Anonymize couvre chaque occurrence de chaque entite
- **Bidirectionnel** : desanonymisation fiable via remplacement par spans, plus reanonymisation rapide par remplacement de chaine
- **Memoire de conversation** : `ConversationMemory` accumule les entites entre les messages pour des placeholders coherents
- **Middleware LangChain** : hooks transparents sur `abefore_model`, `aafter_model`, et `awrap_tool_call` zero modification de votre code d'agent
- **Injection de dependances** : chaque etape du pipeline est un protocole swappable detector, span resolver, entity linker, entity resolver, anonymizer, placeholder factory
- **Modeles immuables** : dataclasses gelees partout (`Entity`, `Detection`, `Span`)

---

## Installation

=== "uv"

    ```bash
    uv add piighost
    ```

=== "pip"

    ```bash
    pip install piighost
    ```

---

## Exemple rapide

```python
import asyncio

from piighost.anonymizer import Anonymizer
from piighost.detector import GlinerDetector
from piighost.entity_linker import ExactEntityLinker
from piighost.entity_resolver import MergeEntityConflictResolver
from piighost.pipeline import AnonymizationPipeline
from piighost.placeholder import CounterPlaceholderFactory
from piighost.span_resolver import ConfidenceSpanConflictResolver

from gliner2 import GLiNER2

model = GLiNER2.from_pretrained("urchade/gliner_multi_pii-v1")

pipeline = AnonymizationPipeline(
    detector=GlinerDetector(model=model, labels=["PERSON", "LOCATION"], threshold=0.5),
    span_resolver=ConfidenceSpanConflictResolver(),
    entity_linker=ExactEntityLinker(),
    entity_resolver=MergeEntityConflictResolver(),
    anonymizer=Anonymizer(CounterPlaceholderFactory()),
)

async def main():
    anonymized, entities = await pipeline.anonymize(
        "Patrick habite a Paris. Patrick aime Paris.",
    )
    print(anonymized)
    # <<PERSON_1>> habite a <<LOCATION_1>>. <<PERSON_1>> aime <<LOCATION_1>>.

asyncio.run(main())
```

!!! note "Telechargement du modele"
    Le modele GLiNER2 est telecharge depuis HuggingFace lors de la premiere utilisation (~500 Mo).

---

## Navigation

| Section | Description |
|---------|-------------|
| [Demarrage rapide](getting-started.md) | Installation et premiers pas |
| [Architecture](architecture.md) | Pipeline et diagrammes de flux |
| [Exemples](examples/basic.md) | Usage basique et integration LangChain |
| [Detecteurs prets a l'emploi](examples/detectors.md) | Patterns regex pour PII courants (US & Europe) |
| [Etendre PIIGhost](extending.md) | Creer ses propres modules |
| [Reference API](reference/anonymizer.md) | Documentation complete de l'API |
