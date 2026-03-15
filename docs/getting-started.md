---
title: Démarrage rapide
---

# Démarrage rapide

## Prérequis

- Python 3.12 ou supérieur
- [`uv`](https://docs.astral.sh/uv/) installé (`pip install uv`)
- Clé API OpenAI (ou Anthropic) configurée dans l'environnement

## Installation

```bash
git clone <repo>
cd aegra
uv sync
```

`uv sync` installe toutes les dépendances déclarées dans `pyproject.toml`, y compris LangGraph, LangChain, GLiNER2 et Langfuse.

## Configuration

Copiez le fichier d'environnement exemple et renseignez vos clés :

```bash
cp .env.example .env
```

Variables minimales requises :

```dotenv
OPENAI_API_KEY=sk-...

# Optionnel — pour le tracing Langfuse
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com
```

## Lancement de l'agent

```bash
uv run python -m aegra.app
```

Le serveur LangGraph démarre et expose l'API de l'agent. Vous pouvez interagir via le playground intégré ou l'API REST.

## Utilisation programmatique

### Avec le middleware complet (recommandé)

```python
from maskara.middleware import PIIAnonymizationMiddleware, PIIState
from langchain.agents import create_agent
from langchain_core.tools import tool


@tool
def get_weather(city: str) -> str:
    """Retourne la météo pour une ville."""
    return f"Il fait 22°C et ensoleillé à {city}."


graph = create_agent(
    model="openai:gpt-4o",
    state_schema=PIIState,
    tools=[get_weather],
    middleware=[PIIAnonymizationMiddleware()],
)

# Invocation
result = graph.invoke(
    {"messages": [{"role": "user", "content": "Quel temps fait-il à Lyon ?"}]},
    config={"configurable": {"thread_id": "session-001"}},
)
print(result["messages"][-1].content)
# → "Il fait 22°C et ensoleillé à Lyon."  (désanonymisé automatiquement)
```

### Avec l'Anonymizer bas niveau

```python
from gliner2 import GLiNER2
from maskara.anonymizer import Anonymizer

extractor = GLiNER2.from_pretrained("fastino/gliner2-base-v1")
anonymizer = Anonymizer(extractor)

# Anonymisation
text = "Apple Inc. CEO Tim Cook a annoncé iPhone 15 à Cupertino."
anon_text, placeholders = anonymizer.anonymize(text, thread_id="thread-001")
print(anon_text)
# → "<COMPANY_1> CEO <PERSON_1> a annoncé <PRODUCT_1> à <LOCATION_1>."

# Désanonymisation
original = anonymizer.deanonymize(anon_text, placeholders)
print(original)
# → "Apple Inc. CEO Tim Cook a annoncé iPhone 15 à Cupertino."
```

## TTL Sweeper (optionnel)

Pour activer la suppression automatique des threads expirés, ajoutez une section `checkpointer` dans `aegra.json` :

```json
{
  "checkpointer": {
    "ttl": {
      "strategy": "delete",
      "sweep_interval_minutes": 60,
      "default_ttl": 1440
    }
  }
}
```

Voir [Configuration](configuration.md) pour tous les paramètres disponibles.

## Prévisualisation de la documentation

```bash
uv run zensical serve
```

Ouvre la documentation en local sur `http://localhost:8000`.
