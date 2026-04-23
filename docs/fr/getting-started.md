---
icon: lucide/rocket
---

# Démarrage rapide

## Installation

### Prérequis

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (recommandé) ou pip

### Installation basique

=== "uv"

    ```bash
    uv add piighost
    ```

=== "pip"

    ```bash
    pip install piighost
    ```

### Installation pour le développement

```bash
git clone https://github.com/Athroniaeth/piighost.git
cd piighost
uv sync
```

---

## Usage 1 : Pipeline standalone

L'usage le plus simple : créer un `AnonymizationPipeline` et l'appeler directement.

```python
import asyncio

from gliner2 import GLiNER2

from piighost.anonymizer import Anonymizer
from piighost.detector import Gliner2Detector
from piighost.linker.entity import ExactEntityLinker
from piighost.entity_resolver import MergeEntityConflictResolver
from piighost.pipeline import AnonymizationPipeline
from piighost.placeholder import CounterPlaceholderFactory
from piighost.span_resolver import ConfidenceSpanConflictResolver

# 1. Charger le modèle NER
model = GLiNER2.from_pretrained("fastino/gliner2-multi-v1")

# 2. Instancier chaque composant
detector = Gliner2Detector(model=model, labels=["PERSON", "LOCATION"], threshold=0.5)
span_resolver = ConfidenceSpanConflictResolver()
entity_linker = ExactEntityLinker()
entity_resolver = MergeEntityConflictResolver()
anonymizer = Anonymizer(CounterPlaceholderFactory())

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
    # <<PERSON_1>> habite à <<LOCATION_1>>. <<PERSON_1>> aime <<LOCATION_1>>.

    # 5. Désanonymiser
    original, _ = await pipeline.deanonymize(anonymized)
    print(original)
    # Patrick habite à Paris. Patrick aime Paris.


asyncio.run(main())
```

!!! info "Labels disponibles"
    Les labels supportés dépendent du modèle GLiNER2 utilisé. Les labels courants incluent `"PERSON"`, `"LOCATION"`, `"ORGANIZATION"`, `"EMAIL"`, `"PHONE"`.

---

## Usage 2 : Pipeline conversationnel avec mémoire

`ThreadAnonymizationPipeline` encapsule le pipeline de base avec une `ConversationMemory` pour accumuler les entités entre les messages et fournir désanonymisation/réanonymisation par remplacement de chaîne.

```python
import asyncio

from piighost.anonymizer import Anonymizer
from piighost.detector.gliner2 import Gliner2Detector
from piighost.linker.entity import ExactEntityLinker
from piighost.resolver import MergeEntityConflictResolver, ConfidenceSpanConflictResolver
from piighost.pipeline import AnonymizationPipeline, ThreadAnonymizationPipeline
from piighost.placeholder import CounterPlaceholderFactory

from gliner2 import GLiNER2

entity_linker = ExactEntityLinker()
entity_resolver = MergeEntityConflictResolver()
span_resolver = ConfidenceSpanConflictResolver()

ph_factory = CounterPlaceholderFactory()
anonymizer = Anonymizer(ph_factory=ph_factory)

model = GLiNER2.from_pretrained("fastino/gliner2-multi-v1")
detector = Gliner2Detector(
    model=model,
    threshold=0.5,
    labels=["PERSON", "LOCATION"],
)
pipeline = ThreadAnonymizationPipeline(
    detector=detector,
    span_resolver=span_resolver,
    entity_linker=entity_linker,
    entity_resolver=entity_resolver,
    anonymizer=anonymizer,
)


async def conversation():
    # Premier message : détection NER + enregistrement des entités
    # la pipeline garde en mémoire que l'entrée et la sortie sont liées,
    # et que <<PERSON_1>> correspond à "Patrick" et <<LOCATION_1>> à "Paris"
    anonymized, _ = await pipeline.anonymize("Patrick habite à Paris.")
    print(anonymized)
    # <<PERSON_1>> habite à <<LOCATION_1>>.

    # Désanonymisation via la correspondance stockée dans le cache de la pipeline
    restored = await pipeline.deanonymize("Bonjour <<PERSON_1>> !")
    print(restored)

    # Désanonymisation par remplacement de texte, utilisant les anciennes détections stockées en mémoire
    restored = await pipeline.deanonymize_with_ent("Bonjour <<PERSON_1>> !")
    print(restored)
    # Bonjour Patrick !

    # Réanonymisation par remplacement de texte, utilisant les anciennes détections stockées en mémoire
    reanon = pipeline.anonymize_with_ent("Résultat pour Patrick à Paris")
    print(reanon)
    # Résultat pour <<PERSON_1>> à <<LOCATION_1>>


asyncio.run(conversation())
```

??? info "Cache SHA-256"
    Le pipeline utilise aiocache avec des clés SHA-256. Si le même texte est soumis plusieurs fois, le résultat mis en cache est retourné sans appel au modèle NER.

---

## Usage 3 : Middleware LangChain

En reprenant le `pipeline` construit ci-dessus (Usage 2), il suffit de l'enrober dans `PIIAnonymizationMiddleware` et de le passer à `create_agent` :

```python
from langchain.agents import create_agent
from piighost.middleware import PIIAnonymizationMiddleware

middleware = PIIAnonymizationMiddleware(pipeline=pipeline)

agent = create_agent(
    model="openai:gpt-5.4",
    tools=[...],
    middleware=[middleware],
)
```

Le middleware intercepte automatiquement chaque tour : le LLM ne voit que du texte anonymisé, les outils reçoivent les vraies valeurs, et les messages affichés à l'utilisateur sont désanonymisés.

Pour un exemple complet (outils, system prompt, observabilité Langfuse, déploiement Aegra), voir [Intégration LangChain](examples/langchain.md).

---

## Utilisation 4 : Client distant

`PIIGhostClient` est un client HTTP asynchrone léger qui délègue toutes les
opérations du pipeline à un serveur `piighost-api` distant. À utiliser quand
le modèle NER doit rester hors de l'hôte applicatif (pod d'inférence dédié,
nœud GPU, service d'anonymisation partagé entre microservices).

```bash
pip install piighost[client]
```

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
        # <<PERSON_1>> habite à <<LOCATION_1>>.

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

Le client reproduit l'API de `ThreadAnonymizationPipeline` (`detect`,
`anonymize`, `deanonymize`, `deanonymize_with_ent`, `override_detections`),
donc remplacer un pipeline local par un pipeline distant se fait en une
ligne.

!!! warning "L'isolation par thread est côté serveur"
    Le paramètre `thread_id` est transmis au serveur et sert à scoper le
    cache et la mémoire de conversation. Réutilisez le même `thread_id`
    pour tous les appels d'une même conversation, sinon les placeholders
    ne seront pas cohérents entre messages.

---

## Commandes de développement

```bash
uv sync  # Installer les dépendances
make lint  # Format (ruff) + lint (ruff) + type-check (pyrefly)
uv run pytest  # Lancer tous les tests
uv run pytest tests/ -k "test_name"  # Lancer un test spécifique
```