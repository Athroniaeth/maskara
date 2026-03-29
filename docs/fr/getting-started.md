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
model = GLiNER2.from_pretrained("fastino/gliner2-multi-v1")

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
from piighost.detector.gliner2 import Gliner2Detector
from piighost.linker.entity import ExactEntityLinker
from piighost.resolver import MergeEntityConflictResolver, ConfidenceSpanConflictResolver
from piighost.pipeline import AnonymizationPipeline, ThreadAnonymizationPipeline, ConversationMemory
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
memory=ConversationMemory()
pipeline = ThreadAnonymizationPipeline(
    detector=detector,
    span_resolver=span_resolver,
    entity_linker=entity_linker,
    entity_resolver=entity_resolver,
    anonymizer=anonymizer,
    memory=memory,
)


async def conversation():
    # Premier message : detection NER + enregistrement des entites
    # la pipeline garde en mémoire que l'entrée et la sortie sont liées, 
    # et que <<PERSON_1>> correspond à "Patrick" et <<LOCATION_1>> à "Paris"
    anonymized, _ = await pipeline.anonymize("Patrick habite a Paris.")
    print(anonymized)
    # <<PERSON_1>> habite a <<LOCATION_1>>.
    
    # Désanonymisation fonctionnant via la correspondance stockée dans le cache de la pipeline
    restored = await pipeline.deanonymize("Bonjour <<PERSON_1>> !")
    print(restored)
    
    # Désanonymisation par remplacement de texte, utilisant les anciennes détéctions stockées en mémoire
    restored = await pipeline.deanonymize_with_ent("Bonjour <<PERSON_1>> !")
    print(restored)
    # Bonjour Patrick !

    # Reanonymisation par remplacement de texte, utilisant les anciennes détéctions stockées en mémoire
    reanon = pipeline.anonymize_with_ent("Resultat pour Patrick a Paris")
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
from piighost.detector.gliner2 import Gliner2Detector
from piighost.linker.entity import ExactEntityLinker
from piighost.resolver import MergeEntityConflictResolver, ConfidenceSpanConflictResolver
from piighost.pipeline import AnonymizationPipeline, ThreadAnonymizationPipeline, ConversationMemory
from piighost.placeholder import CounterPlaceholderFactory
from piighost.middleware import PIIAnonymizationMiddleware

from gliner2 import GLiNER2



@tool
def send_email(to: str, subject: str, body: str) -> str:
    """Envoie un email a l'adresse donnee."""
    return f"Email envoyé a {to}."


# Construire le pipeline conversationnel
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
memory=ConversationMemory()
pipeline = ThreadAnonymizationPipeline(
    detector=detector,
    span_resolver=span_resolver,
    entity_linker=entity_linker,
    entity_resolver=entity_resolver,
    anonymizer=anonymizer,
    memory=memory,
)
middleware = PIIAnonymizationMiddleware(pipeline=pipeline)

system_prompt = """\
You are a helpful assistant. Some inputs may contain anonymized placeholders that replace real values for privacy reasons.

Rules:
1. Treat every placeholder as if it were the real value, never comment on its format, never say it is a token, never ask the user to reveal it.
2. Placeholders can be passed directly to tools use them as-is as input arguments. This preserves the user's privacy while \
still allowing tools to operate.
3. If the user asks for a specific detail about a token (e.g. "what is the first letter?"), reply briefly: "I cannot answer that question as the data has been anonymized to protect your personal information." \
Another example is if the user asks "Dans quel pays ce trouve la ville de {city} ?", you can answer "Je suis désolé, mais je ne peux pas répondre à cette question car les données ont été anonymisées pour protéger vos informations personnelles."
"""

# Créer l'agent avec le middleware
agent = create_agent(
    model="openai:gpt-5.4",
    system_prompt=system_prompt,
    tools=[send_email],
    middleware=[middleware],
)
```

Le middleware intercepte automatiquement chaque tour de l'agent le LLM ne voit que du texte anonymise, les outils recoivent les vraies valeurs, et les messages affiches a l'utilisateur sont desanonymises.

---

## Commandes de développement

```bash
uv sync  # Installer les dépendances
make lint  # Format (ruff) + lint (ruff) + type-check (pyrefly)
uv run pytest  # Lancer tous les tests
uv run pytest tests/ -k "test_name"  # Lancer un test spécifique
```
