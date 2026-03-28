---
icon: lucide/rocket
---

# Demarrage rapide

## Installation

### Prerequis

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (recommande) ou pip

### Installation basique

=== "uv"

    ```bash
    uv add piighost
    ```

=== "pip"

    ```bash
    pip install piighost
    ```

### Installation pour le developpement

```bash
git clone https://github.com/Athroniaeth/piighost.git
cd piighost
uv sync
```

---

## Usage 1 Pipeline standalone

L'usage le plus simple : creer un `AnonymizationPipeline` et l'appeler directement.

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

# 1. Charger le modele NER
model = GLiNER2.from_pretrained("urchade/gliner_multi_pii-v1")

# 2. Construire le pipeline
pipeline = AnonymizationPipeline(
    detector=Gliner2Detector(model=model, labels=["PERSON", "LOCATION"], threshold=0.5),
    span_resolver=ConfidenceSpanConflictResolver(),
    entity_linker=ExactEntityLinker(),
    entity_resolver=MergeEntityConflictResolver(),
    anonymizer=Anonymizer(CounterPlaceholderFactory()),
)


async def main():
    # 3. Anonymiser
    anonymized, entities = await pipeline.anonymize(
        "Patrick habite a Paris. Patrick aime Paris.",
    )
    print(anonymized)
    # <<PERSON_1>> habite a <<LOCATION_1>>. <<PERSON_1>> aime <<LOCATION_1>>.

    # 4. Desanonymiser
    original, _ = await pipeline.deanonymize(anonymized)
    print(original)
    # Patrick habite a Paris. Patrick aime Paris.


asyncio.run(main())
```

!!! info "Labels disponibles"
    Les labels supportes dependent du modele GLiNER2 utilise. Les labels courants incluent `"PERSON"`, `"LOCATION"`, `"ORGANIZATION"`, `"EMAIL"`, `"PHONE"`.

---

## Usage 2 Pipeline conversationnel avec memoire

`ConversationAnonymizationPipeline` encapsule le pipeline de base avec une `ConversationMemory` pour accumuler les entites entre les messages et fournir desanonymisation/reanonymisation par remplacement de chaine.

```python
import asyncio

from piighost.anonymizer import Anonymizer
from piighost.conversation_memory import ConversationMemory
from piighost.conversation_pipeline import ConversationAnonymizationPipeline
from piighost.detector import Gliner2Detector
from piighost.linker.entity import ExactEntityLinker
from piighost.entity_resolver import MergeEntityConflictResolver
from piighost.placeholder import CounterPlaceholderFactory
from piighost.span_resolver import ConfidenceSpanConflictResolver

conv_pipeline = ConversationAnonymizationPipeline(
    detector=Gliner2Detector(model=model, labels=["PERSON", "LOCATION"], threshold=0.5),
    span_resolver=ConfidenceSpanConflictResolver(),
    entity_linker=ExactEntityLinker(),
    entity_resolver=MergeEntityConflictResolver(),
    anonymizer=Anonymizer(CounterPlaceholderFactory()),
    memory=ConversationMemory(),
)


async def conversation():
    # Premier message : detection NER + enregistrement des entites
    anonymized, _ = await conv_pipeline.anonymize("Patrick habite a Paris.")
    print(anonymized)
    # <<PERSON_1>> habite a <<LOCATION_1>>.

    # Desanonymisation par remplacement de chaine (fonctionne sur tout texte avec tokens)
    restored = await conv_pipeline.deanonymize_with_ent("Bonjour <<PERSON_1>> !")
    print(restored)
    # Bonjour Patrick !

    # Reanonymisation (valeurs originales → tokens)
    reanon = conv_pipeline.anonymize_with_ent("Resultat pour Patrick a Paris")
    print(reanon)
    # Resultat pour <<PERSON_1>> a <<LOCATION_1>>


asyncio.run(conversation())
```

??? info "Cache SHA-256"
    Le pipeline utilise aiocache avec des cles SHA-256. Si le meme texte est soumis plusieurs fois, le resultat mis en cache est retourne sans appel au modele NER.

---

## Usage 3 Middleware LangChain

Pour integrer l'anonymisation dans un agent LangGraph, utilisez `PIIAnonymizationMiddleware` :

```python
from langchain.agents import create_agent
from langchain_core.tools import tool

from piighost.anonymizer import Anonymizer
from piighost.conversation_memory import ConversationMemory
from piighost.conversation_pipeline import ConversationAnonymizationPipeline
from piighost.detector import Gliner2Detector
from piighost.linker.entity import ExactEntityLinker
from piighost.entity_resolver import MergeEntityConflictResolver
from piighost.middleware import PIIAnonymizationMiddleware
from piighost.placeholder import CounterPlaceholderFactory
from piighost.span_resolver import ConfidenceSpanConflictResolver


@tool
def send_email(to: str, subject: str, body: str) -> str:
    """Envoie un email a l'adresse donnee."""
    return f"Email envoye a {to}."


# Construire le pipeline conversationnel
pipeline = ConversationAnonymizationPipeline(
    detector=Gliner2Detector(model=model, labels=["PERSON", "LOCATION"], threshold=0.5),
    span_resolver=ConfidenceSpanConflictResolver(),
    entity_linker=ExactEntityLinker(),
    entity_resolver=MergeEntityConflictResolver(),
    anonymizer=Anonymizer(CounterPlaceholderFactory()),
    memory=ConversationMemory(),
)
middleware = PIIAnonymizationMiddleware(pipeline=pipeline)

# Creer l'agent avec le middleware
agent = create_agent(
    model="openai:gpt-4o-mini",
    system_prompt="Tu es un assistant utile.",
    tools=[send_email],
    middleware=[middleware],
)
```

Le middleware intercepte automatiquement chaque tour de l'agent le LLM ne voit que du texte anonymise, les outils recoivent les vraies valeurs, et les messages affiches a l'utilisateur sont desanonymises.

---

## Commandes de developpement

```bash
uv sync                      # Installer les dependances
make lint                    # Format (ruff) + lint (ruff) + type-check (pyrefly)
uv run pytest                # Lancer tous les tests
uv run pytest tests/ -k "test_name"  # Lancer un test specifique
```
