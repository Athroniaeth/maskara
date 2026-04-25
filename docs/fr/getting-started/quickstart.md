---
icon: lucide/zap
---

# Quickstart

Le chemin le plus court pour voir `piighost` à l'œuvre : aucun modèle à télécharger, pas d'inférence, juste un dictionnaire fixe. Idéal pour essayer la librairie en moins d'une minute.

```python
import asyncio

from piighost import Anonymizer, ExactMatchDetector
from piighost.pipeline import AnonymizationPipeline

detector = ExactMatchDetector([("Patrick", "PERSON"), ("Paris", "LOCATION")])
pipeline = AnonymizationPipeline(detector=detector, anonymizer=Anonymizer())


async def main():
    anonymized, _ = await pipeline.anonymize("Patrick habite à Paris.")
    print(anonymized)
    # <<PERSON:1>> habite à <<LOCATION:1>>.


asyncio.run(main())
```

`ExactMatchDetector` repère les occurrences exactes (aux frontières de mots) des paires `(texte, label)` fournies. `AnonymizationPipeline` applique des valeurs par défaut raisonnables pour les trois étapes intermédiaires : résolution de chevauchements, liaison d'entités, fusion des groupes. C'est suffisant pour un premier essai.

!!! tip "Et ensuite ?"
    - Pour une vraie détection automatique (noms et lieux arbitraires), passez au [Premier pipeline](first-pipeline.md) avec un NER comme GLiNER2.
    - Pour détecter des formats structurés (emails, IPs, numéros de carte) sans NER, voir les [Détecteurs prêts à l'emploi](../examples/detectors.md).
    - Pour anonymiser au fil d'une conversation avec mémoire persistante, voir le [Pipeline conversationnel](conversation.md).
