---
title: Demarrage rapide
---

# Demarrage rapide

## Prerequis

- Python 3.12 ou superieur
- [`uv`](https://docs.astral.sh/uv/) installe
- Cle API OpenAI (ou Anthropic) configuree dans `.env`
- PostgreSQL (via Docker ou installation locale)

## Installation

```bash
git clone <repo>
cd maskara
uv sync
```

## Configuration

Copiez le fichier d'environnement exemple et renseignez vos cles :

```bash
cp .env.example .env
```

Variables minimales requises :

```dotenv
OPENAI_API_KEY=sk-...

# Base de donnees
POSTGRES_USER=maskara
POSTGRES_PASSWORD=maskara_secret
POSTGRES_DB=maskara
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
```

## Base de donnees

Demarrez PostgreSQL via Docker :

```bash
docker compose up postgres -d
```

Cela lance un conteneur `pgvector/pgvector:pg18` avec les credentials de votre `.env`.

Si le conteneur existait deja avec d'autres credentials, supprimez le volume et relancez :

```bash
docker compose down -v
docker compose up postgres -d
```

## Lancement

### Application complete (Docker)

```bash
docker compose up --build
```

### Developpement local

```bash
uv run python -m maskara.app
```

Le serveur demarre sur `http://localhost:{PORT}` (defaut: 8000).

## Utilisation programmatique

### Avec le middleware LangGraph (production)

```python
from maskara.middleware import PIIAnonymizationMiddleware, PIIState
from langchain.agents import create_agent
from langchain_core.tools import tool


@tool
def get_weather(city: str) -> str:
    """Retourne la meteo pour une ville."""
    return f"Il fait 22C a {city}."


graph = create_agent(
    model="openai:gpt-4o",
    state_schema=PIIState,
    tools=[get_weather],
    middleware=[PIIAnonymizationMiddleware()],
)

result = graph.invoke(
    {"messages": [{"role": "user", "content": "Quel temps fait-il a Lyon ?"}]},
    config={"configurable": {"thread_id": "session-001"}},
)
print(result["messages"][-1].content)
# "Il fait 22C a Lyon."  (desanonymise automatiquement)
```

### Avec l'Anonymizer (bas niveau)

```python
from gliner2 import GLiNER2
from maskara.anonymizer import Anonymizer

extractor = GLiNER2.from_pretrained("fastino/gliner2-base-v1")
anonymizer = Anonymizer(extractor)

# Anonymisation
text = "Apple Inc. CEO Tim Cook a annonce iPhone 15 a Cupertino."
anon_text, vocab = anonymizer.anonymize(text, thread_id="thread-001")
print(anon_text)
# "<COMPANY_1> CEO <PERSON_1> a annonce <PRODUCT_1> a <LOCATION_1>."

# Desanonymisation
original = anonymizer.deanonymize(anon_text, vocab)
print(original)
# "Apple Inc. CEO Tim Cook a annonce iPhone 15 a Cupertino."
```

## Documentation locale

```bash
uv run zensical serve
```

Ouvre la documentation sur `http://localhost:8000`.
