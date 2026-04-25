---
icon: lucide/cloud
---

# Client distant

`PIIGhostClient` est un client HTTP asynchrone léger qui délègue toutes les opérations du pipeline à un serveur `piighost-api` distant. À utiliser quand le modèle NER doit rester hors de l'hôte applicatif (pod d'inférence dédié, nœud GPU, service d'anonymisation partagé entre microservices).

## Installation

```bash
pip install piighost[client]
```

## Usage

```python
import asyncio

from piighost.client import PIIGhostClient
from piighost.exceptions import CacheMissError


async def main():
    async with PIIGhostClient(
        base_url="http://piighost-api.internal:8000",
        api_key="ak_v1-...",
    ) as client:
        text, entities = await client.anonymize(
            "Patrick habite à Paris.",
            thread_id="user-42",
        )
        print(text)
        # <<PERSON:1>> habite à <<LOCATION:1>>.

        try:
            original, _ = await client.deanonymize(text, thread_id="user-42")
        except CacheMissError:
            # Le serveur n'a pas de mapping en cache pour ce thread
            # (redémarrage, éviction, mauvais thread_id). Fallback sur
            # le remplacement par entité, qui fonctionne sur n'importe
            # quel texte contenant des placeholders.
            original = await client.deanonymize_with_ent(text, thread_id="user-42")
        print(original)


asyncio.run(main())
```

Le client reproduit l'API de `ThreadAnonymizationPipeline` (`detect`, `anonymize`, `deanonymize`, `deanonymize_with_ent`, `override_detections`), donc remplacer un pipeline local par un pipeline distant se fait en une ligne.

!!! warning "L'isolation par thread est côté serveur"
    Le paramètre `thread_id` est transmis au serveur et sert à scoper le cache et la mémoire de conversation. Réutilisez le même `thread_id` pour tous les appels d'une même conversation, sinon les placeholders ne seront pas cohérents entre messages.

Pour le déploiement du serveur, voir [Déploiement](../deployment.md).
