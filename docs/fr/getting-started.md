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
    uv add maskara
    ```

=== "pip"

    ```bash
    pip install maskara
    ```

### Installation pour le développement

```bash
git clone https://github.com/Athroniaeth/maskara.git
cd maskara
uv sync
```

---

## Usage 1 Anonymisation standalone

L'usage le plus simple : créer un `Anonymizer` et l'appeler directement.

```python
from gliner2 import GLiNER2
from maskara.anonymizer import Anonymizer, GlinerDetector

# 1. Charger le modèle NER
model = GLiNER2.from_pretrained("fastino/gliner2-multi-v1")

# 2. Créer le détecteur
detector = GlinerDetector(model=model, threshold=0.5, flat_ner=True)

# 3. Créer l'anonymiseur
anonymizer = Anonymizer(detector=detector)

# 4. Anonymiser
result = anonymizer.anonymize(
    "Patrick habite à Paris. Patrick aime Paris.",
    labels=["PERSON", "LOCATION"],
)

print(result.anonymized_text)
# <<PERSON_1>> habite à <<LOCATION_1>>. <<PERSON_1>> aime <<LOCATION_1>>.

# 5. Désanonymiser
original = anonymizer.deanonymize(result)
print(original)
# Patrick habite à Paris. Patrick aime Paris.
```

!!! info "Labels disponibles"
    Les labels supportés dépendent du modèle GLiNER2 utilisé. `"fastino/gliner2-multi-v1"` supporte notamment `"PERSON"`, `"LOCATION"`, `"ORGANIZATION"`, `"EMAIL"`, `"PHONE"`.

---

## Usage 2 Pipeline avec cache de session

`AnonymizationPipeline` encapsule l'`Anonymizer` avec un cache de session pour réutiliser les placeholders entre plusieurs messages.

```python
import asyncio
from maskara.pipeline import AnonymizationPipeline

pipeline = AnonymizationPipeline(
    anonymizer=anonymizer,
    labels=["PERSON", "LOCATION"],
)

async def main():
    # Anonymisation (async, avec cache)
    result = await pipeline.anonymize("Patrick habite à Paris.")
    print(result.anonymized_text)
    # <<PERSON_1>> habite à <<LOCATION_1>>.

    # Désanonymisation synchrone par remplacement de chaîne
    restored = pipeline.deanonymize_text("<<PERSON_1>> habite à <<LOCATION_1>>.")
    print(restored)
    # Patrick habite à Paris.

    # Reanonymisation (inverse : original → placeholder)
    reanon = pipeline.reanonymize_text("Résultat pour Patrick à Paris")
    print(reanon)
    # Résultat pour <<PERSON_1>> à <<LOCATION_1>>

asyncio.run(main())
```

??? info "Cache SHA-256"
    Le pipeline calcule un hash SHA-256 du texte source. Si le même texte est soumis plusieurs fois, le résultat mis en cache est retourné immédiatement sans appel au modèle NER.

---

## Usage 3 Middleware LangChain

Pour intégrer l'anonymisation dans un agent LangGraph, utilisez `PIIAnonymizationMiddleware` :

```python
from langchain.agents import create_agent
from langchain_core.tools import tool

from maskara.anonymizer import Anonymizer, GlinerDetector
from maskara.middleware import PIIAnonymizationMiddleware
from maskara.pipeline import AnonymizationPipeline

@tool
def send_email(to: str, subject: str, body: str) -> str:
    """Envoie un email à l'adresse donnée."""
    return f"Email envoyé à {to}."

# Construire la stack d'anonymisation
detector = GlinerDetector(model=model, threshold=0.5, flat_ner=True)
anonymizer = Anonymizer(detector=detector)
pipeline = AnonymizationPipeline(anonymizer=anonymizer, labels=["PERSON", "LOCATION"])
middleware = PIIAnonymizationMiddleware(pipeline=pipeline)

# Créer l'agent avec le middleware
agent = create_agent(
    model="openai:gpt-4o-mini",
    system_prompt="Tu es un assistant utile.",
    tools=[send_email],
    middleware=[middleware],
)
```

Le middleware intercepte automatiquement chaque tour de l'agent le LLM ne voit que du texte anonymisé, les outils reçoivent les vraies valeurs, et les messages affichés à l'utilisateur sont désanonymisés.

---

## Commandes de développement

```bash
uv sync                      # Installer les dépendances
make lint                    # Format (ruff) + lint (ruff) + type-check (pyrefly)
uv run pytest                # Lancer tous les tests
uv run pytest tests/ -k "test_name"  # Lancer un test spécifique
```
