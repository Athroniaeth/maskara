---
icon: lucide/shield
---

# PIIGhost

**Anonymisation transparente des donnees personnelles pour agents LLM.**

`piighost` est une librairie Python qui permet de détecter les PII (personal identifiable information), de les extraires, d'appliquer des correctifs et de les anonymiser et desanonymiser automatiquement les entites sensibles (noms, lieux, etc.). Avec des modules pour permettre l'anonymisation bidirectionnelle dans les conversations d'agents IA. Elle peut s'intégrer via un middleware LangChain sans modifier votre code d'agent existant.

---

## Fonctionnalités

- **Detection** : Détecter les PII avec des modèles NER, des algorithmes et faite votre configuration personnalisé avec notre composant de composition de détecteurs
- **Resolution de spans** : Résoudre les conflits de spans détectés (chevauchement, imbriqué) pour garantir des entités propres et non redondantes, surtout quand on utilise plusieurs détecteurs
- **Liaison d'entités** : Lier les différentes detections, cela permet d'avoir une tolérance aux fautes d'orthographe et de capturer des mentions qu'un modèle NER pourrait manquer
- **Resolution d'entités** : Résoudre les conflits d'entités liées (un détecteur détecte A et B comme une même entité, ou un détecteur lie A et B mais un autre détecteur lie B et C) pour garantir des entités finales cohérentes
- **Anonymisation** : Anonymise les entités détectées avec des placeholders personnalisables (ex: <<PERSON_1>>, <<LOCATION_1>>) pour protéger la confidentialité tout en préservant la structure du texte. Un système de cache permet de garder en mémoire l'anonymisation appliqué, et peu donc revenir en arrière pour désanonymiser.
- **Placeholder Factory** : Créez des placeholders personnalisés pour l'anonymisation, avec des stratégies de nommage flexibles (compteurs, UUID, etc.) pour s'adapter à vos besoins spécifiques
- **Middleware** : Intégrez facilement `piighost` dans vos agents LangChain pour une anonymisation transparente avant et après les appels de modèle, sans modifier votre code d'agent existant

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
from piighost.detector.gliner2 import Gliner2Detector
from piighost.linker.entity import ExactEntityLinker
from piighost.resolver import MergeEntityConflictResolver, ConfidenceSpanConflictResolver
from piighost.pipeline import AnonymizationPipeline
from piighost.placeholder import CounterPlaceholderFactory

from gliner2 import GLiNER2
 
entity_linker=ExactEntityLinker()
entity_resolver=MergeEntityConflictResolver()
span_resolver=ConfidenceSpanConflictResolver()

ph_factory = CounterPlaceholderFactory()
anonymizer = Anonymizer(ph_factory=ph_factory)

model = GLiNER2.from_pretrained("fastino/gliner2-multi-v1")
detector=Gliner2Detector(
    model=model, 
    threshold=0.5, 
    labels=["PERSON", "LOCATION"],
)

pipeline = AnonymizationPipeline(
    detector=detector,
    span_resolver=span_resolver,
    entity_linker=entity_linker,
    entity_resolver=entity_resolver,
    anonymizer=anonymizer,
)


async def main():
    text = "Patrick lives in Paris. Patrick loves Paris."
    anonymized, entities = await pipeline.anonymize(text)
    print(anonymized)
    # <<PERSON_1>> lives in <<LOCATION_1>>. <<PERSON_1>> loves <<LOCATION_1>>.


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
