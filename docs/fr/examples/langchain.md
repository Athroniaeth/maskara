---
icon: lucide/link
---

# Intégration LangChain v1

Cette page présente l'intégration complète de PIIGhost dans un agent LangGraph, basée sur l'exemple disponible dans [`examples/graph/`](https://github.com/Athroniaeth/piighost/tree/main/examples/graph).

---

## Installation

Pour utiliser le middleware LangChain, installez les dépendances supplémentaires :

=== "uv"

    ```bash
    uv add piighost langchain langgraph langchain-openai
    ```

=== "pip"

    ```bash
    pip install piighost langchain langgraph langchain-openai
    ```

!!! warning "Dépendance optionnelle"
    `PIIAnonymizationMiddleware` importe `langchain` au moment de son instanciation. Si `langchain` n'est pas installé, une `ImportError` explicite est levée avec le message `"You must install piighost[langchain] for use middleware"`.

---

## Structure de l'intégration

```
GLiNER2 model
    └── GlinerDetector
            └── Anonymizer
                    └── AnonymizationPipeline
                                └── PIIAnonymizationMiddleware
                                            └── create_agent(middleware=[...])
```

---

## Exemple complet

```python
from dotenv import load_dotenv
from gliner2 import GLiNER2
from langchain.agents import create_agent
from langchain_core.tools import tool

from piighost.anonymizer import Anonymizer, GlinerDetector
from piighost.middleware import PIIAnonymizationMiddleware
from piighost.pipeline import AnonymizationPipeline

load_dotenv()

# ---------------------------------------------------------------------------
# 1. Définir les outils de l'agent
# ---------------------------------------------------------------------------

@tool
def send_email(to: str, subject: str, body: str) -> str:
    """Envoie un email à l'adresse donnée.

    Args:
        to: Adresse email du destinataire.
        subject: Objet de l'email.
        body: Corps du message.

    Returns:
        Confirmation d'envoi.
    """
    return f"Email envoyé à {to}."


@tool
def get_weather(country_or_city: str) -> str:
    """Retourne la météo actuelle pour un lieu donné.

    Args:
        country_or_city: Nom de la ville ou du pays.

    Returns:
        Résumé météo.
    """
    return f"Il fait 22°C et ensoleillé à {country_or_city}."


# ---------------------------------------------------------------------------
# 2. Configurer le system prompt pour les placeholders
# ---------------------------------------------------------------------------

system_prompt = """\
Tu es un assistant utile. Certaines entrées peuvent contenir des placeholders \
anonymisés qui remplacent des valeurs réelles pour des raisons de confidentialité.

Règles :
1. Traite chaque placeholder comme s'il était la vraie valeur. Ne commente jamais \
son format, ne dis pas que c'est un token, ne demande pas à l'utilisateur de le révéler.
2. Les placeholders peuvent être passés directement aux outils. Cela préserve la \
confidentialité de l'utilisateur tout en permettant aux outils de fonctionner.
3. Si l'utilisateur demande un détail spécifique sur un placeholder \
(ex: "quelle est la première lettre ?"), réponds brièvement : "Je ne peux pas \
répondre à cette question car les données ont été anonymisées pour protéger vos \
informations personnelles."
"""

# ---------------------------------------------------------------------------
# 3. Initialiser la stack d'anonymisation
# ---------------------------------------------------------------------------

# Charger le modèle GLiNER2 (téléchargement HuggingFace ~500 Mo à la première exécution)
extractor = GLiNER2.from_pretrained("fastino/gliner2-multi-v1")

detector = GlinerDetector(model=extractor, threshold=0.5, flat_ner=True)
anonymizer = Anonymizer(detector=detector)
pipeline = AnonymizationPipeline(
    anonymizer=anonymizer,
    labels=["PERSON", "LOCATION"],
)
middleware = PIIAnonymizationMiddleware(pipeline=pipeline)

# ---------------------------------------------------------------------------
# 4. Créer l'agent LangGraph avec le middleware
# ---------------------------------------------------------------------------

graph = create_agent(
    model="openai:gpt-4o-mini",
    system_prompt=system_prompt,
    tools=[send_email, get_weather],
    middleware=[middleware],
)
```

---

## Comment fonctionne le middleware

Le `PIIAnonymizationMiddleware` intercepte chaque tour de l'agent en trois points :

### `abefore_model` avant le LLM

```
Utilisateur : "Envoie un email à Patrick à Paris"
      ↓
Middleware  : détection NER sur HumanMessage
            → "Envoie un email à <<PERSON_1>> à <<LOCATION_1>>"
      ↓
LLM voit   : "Envoie un email à <<PERSON_1>> à <<LOCATION_1>>"
```

### `awrap_tool_call` autour des outils

```
LLM appelle  : send_email(to="<<PERSON_1>>", subject="...", body="...")
      ↓
Middleware   : désanonymise les args
             → send_email(to="Patrick", subject="...", body="...")
      ↓
Outil reçoit : to="Patrick"  ← vraie valeur
      ↓
Outil retourne: "Email envoyé à Patrick."
      ↓
Middleware   : reanonymise la réponse
             → "Email envoyé à <<PERSON_1>>."
      ↓
LLM voit     : "Email envoyé à <<PERSON_1>>."
```

### `aafter_model` après le LLM

```
LLM répond   : "C'est fait ! Email envoyé à <<PERSON_1>>."
      ↓
Middleware   : désanonymise tous les messages
             → "C'est fait ! Email envoyé à Patrick."
      ↓
Utilisateur  : "C'est fait ! Email envoyé à Patrick."
```

---

## Utiliser l'agent

```python
import asyncio

async def main():
    response = await graph.ainvoke({
        "messages": [{"role": "user", "content": "Envoie un email à Patrick à Paris"}]
    })
    print(response["messages"][-1].content)
    # C'est fait ! Email envoyé à Patrick.

asyncio.run(main())
```

---

## Avec Langfuse (observabilité)

L'exemple complet inclut l'intégration Langfuse pour tracer les appels LLM :

```python
from langfuse import get_client
from langfuse.langchain import CallbackHandler

langfuse = get_client()
langfuse_handler = CallbackHandler()

graph = create_agent(
    model="openai:gpt-4o-mini",
    system_prompt=system_prompt,
    tools=[send_email, get_weather],
    middleware=[middleware],
    callbacks=[langfuse_handler],  # (1)!
)
```

1. Les callbacks Langfuse s'ajoutent à `create_agent`. Toutes les interactions LLM sont tracées avec les textes **anonymisés** (le traçage ne voit jamais de données personnelles).

---

## Déploiement avec Aegra

L'exemple `examples/graph/` est conçu pour être déployé avec [Aegra](https://aegra.dev/) (alternative auto-hébergée à LangSmith).

Fichier `aegra.json` :

```json
{
  "graph": "./src/graph/graph.py:graph",
  "http": "./src/graph/app.py:app",
  "ttl": {
    "interval_minutes": 60,
    "default_minutes": 20160
  }
}
```

```bash
# Démarrer le serveur de développement (graph + FastAPI sur le port 8000)
uv run aegra dev

# Stack complète avec PostgreSQL
docker compose up --build
```

---

## Variables d'environnement

Copiez `.env.example` en `.env` et renseignez :

```bash
# LLM
OPENAI_API_KEY=sk-...
# ou
ANTHROPIC_API_KEY=sk-ant-...

# Aegra (obligatoire)
AEGRA_CONFIG=aegra.json

# Base de données
DATABASE_URL=postgresql://user:pass@localhost:5432/piighost

# Observabilité (optionnel)
LANGFUSE_PUBLIC_KEY=...
LANGFUSE_SECRET_KEY=...
```
