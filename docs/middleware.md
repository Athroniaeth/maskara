---
title: Middleware — Référence API
---

# Middleware

`src/maskara/middleware.py`

Le middleware d'anonymisation PII s'intègre dans LangGraph via le mécanisme de hooks d'`AgentMiddleware`. Il intercepte toutes les communications entre l'utilisateur, le LLM et les outils pour garantir qu'aucune donnée personnelle ne transite en clair vers le modèle.

---

## `PIIState`

```python
class PIIState(AgentState):
    pii_to_token: Annotated[dict[str, str], _merge_dicts]
    pii_to_original: Annotated[dict[str, str], _merge_dicts]
```

Extension de `AgentState` qui persiste le mapping bidirectionnel PII ↔ jetons dans le checkpoint LangGraph.

| Champ | Description |
|-------|-------------|
| `pii_to_token` | `{"Lyon": "<LOCATION:e5f6a7b8>", "Tim Cook": "<PERSON:a1b2c3d4>"}` |
| `pii_to_original` | `{"<LOCATION:e5f6a7b8>": "Lyon", "<PERSON:a1b2c3d4>": "Tim Cook"}` |

!!! info
    Ce state est checkpointé par LangGraph, ce qui garantit la cohérence des jetons même après redémarrage du serveur, tant que le `thread_id` est préservé.

---

## Format des jetons

```
<ENTITY_TYPE:xxxxxxxx>
```

- `ENTITY_TYPE` : `PERSON`, `LOCATION`, `ORGANIZATION`, `EMAIL_ADDRESS`, `PHONE_NUMBER`
- `xxxxxxxx` : 8 premiers caractères hexadécimaux du SHA-256 de la valeur originale

**Déterminisme :** `"Lyon"` produit toujours `<LOCATION:e5f6a7b8>`, indépendamment du thread ou de la session.

---

## `PIIAnonymizationMiddleware`

```python
class PIIAnonymizationMiddleware(AgentMiddleware):
    def __init__(
        self,
        analyzed_fields: list[str] | None = None,
        gliner_model: str = "fastino/gliner2-large-v1",
        threshold: float = 0.4,
        language: str = "fr",
    )
```

| Paramètre | Défaut | Description |
|-----------|--------|-------------|
| `analyzed_fields` | `["PERSON", "LOCATION", "ORGANIZATION", "EMAIL_ADDRESS", "PHONE_NUMBER"]` | Types d'entités à anonymiser |
| `gliner_model` | `"fastino/gliner2-large-v1"` | Modèle HuggingFace GLiNER2 |
| `threshold` | `0.4` | Score de confiance minimum (plus bas = plus de rappel, plus de faux positifs) |
| `language` | `"fr"` | Code langue passé au modèle NER |

---

## Utilisation

```python
from maskara.middleware import PIIAnonymizationMiddleware, PIIState
from langchain.agents import create_agent

graph = create_agent(
    model="openai:gpt-4o",
    state_schema=PIIState,
    tools=[...],
    middleware=[PIIAnonymizationMiddleware()],
)
```

---

## Hooks

### `before_model(state, runtime)`

```python
def before_model(self, state: PIIState, runtime: Runtime) -> dict[str, Any] | None
```

Exécuté **avant chaque appel LLM**. Traite les messages dans l'ordre suivant :

1. **Dernier `HumanMessage`** : anonymisation complète via GLiNER2
2. **`ToolMessage`s après le dernier `AIMessage`** : anonymisation complète (les résultats d'outils sont stockés bruts par `wrap_tool_call`)
3. **`AIMessage`s** : ré-application des mappings connus uniquement (sans GLiNER2) pour restaurer l'anonymisation après `after_agent`

**Retourne :** Patch d'état avec les messages mis à jour et les nouvelles entrées de mapping, ou `None` si rien n'a changé.

Version async : `abefore_model(state, runtime)`

---

### `wrap_tool_call(request, handler)`

```python
def wrap_tool_call(
    self,
    request: ToolCallRequest,
    handler: Callable[[ToolCallRequest], ToolMessage | Command],
) -> ToolMessage | Command
```

Exécuté **autour de chaque appel d'outil** :

1. Désanonymise les arguments de l'outil (`str` uniquement)
2. Exécute l'outil avec les vraies valeurs
3. Retourne le résultat **brut** (non anonymisé)

!!! note
    Le résultat brut est intentionnel. `before_model` l'anonymisera au tour suivant avant que le LLM ne le lise.

**Retourne :** `ToolMessage` brut ou `Command` inchangé.

Version async : `awrap_tool_call(request, handler)`

---

### `after_agent(state, runtime)`

```python
def after_agent(self, state: PIIState, runtime: Runtime) -> dict[str, Any] | None
```

Exécuté **après la réponse finale de l'agent**. Désanonymise le dernier `AIMessage` afin que l'utilisateur reçoive les vraies valeurs.

**Retourne :** Patch d'état avec le message désanonymisé, ou `None` si rien n'a changé.

Version async : `aafter_agent(state, runtime)`

---

## Méthodes publiques

### `anonymize(text)`

```python
def anonymize(self, text: str) -> str
```

Détecte les PII dans `text` et remplace chaque span par un jeton déterministe.

**Algorithme :**

1. Remplace les valeurs déjà connues (via le cache `_to_token`)
2. Masque les jetons existants avec des placeholders null-byte pour éviter la re-détection
3. Lance GLiNER2 sur le texte masqué
4. Crée ou réutilise un jeton pour chaque nouvelle entité
5. Restaure les jetons masqués

---

### `deanonymize(text)`

```python
def deanonymize(self, text: str) -> str
```

Remplace tous les jetons `<TYPE:hash>` dans `text` par leurs valeurs originales.

---

## Entités supportées

| Label GLiNER2 | Type jeton | Exemple |
|---------------|------------|---------|
| `person` | `PERSON` | `<PERSON:a1b2c3d4>` |
| `location` | `LOCATION` | `<LOCATION:e5f6a7b8>` |
| `organization` | `ORGANIZATION` | `<ORGANIZATION:12345678>` |
| `email address` | `EMAIL_ADDRESS` | `<EMAIL_ADDRESS:abcdef01>` |
| `phone number` | `PHONE_NUMBER` | `<PHONE_NUMBER:23456789>` |

---

## Exemple bout-en-bout

```python
from maskara.middleware import PIIAnonymizationMiddleware, PIIState
from langchain.agents import create_agent
from langchain_core.tools import tool


@tool
def send_email(to: str, subject: str, body: str) -> str:
    """Envoie un email."""
    return f"Email envoyé à {to}."


middleware = PIIAnonymizationMiddleware(
    threshold=0.4,
    language="fr",
)

graph = create_agent(
    model="openai:gpt-4o",
    state_schema=PIIState,
    tools=[send_email],
    middleware=[middleware],
)

# L'utilisateur envoie un message avec des données personnelles
result = graph.invoke(
    {
        "messages": [{
            "role": "user",
            "content": "Envoie un email à pierre@example.com pour lui souhaiter bon anniversaire.",
        }]
    },
    config={"configurable": {"thread_id": "session-abc"}},
)

# La réponse finale est désanonymisée automatiquement
print(result["messages"][-1].content)
# → "J'ai envoyé un email à pierre@example.com pour lui souhaiter bon anniversaire."
```

!!! warning "Limitation actuelle"
    Le middleware ne supporte que les messages dont le `content` est une `str` ou une `list` de blocs texte. Les messages multimodaux (images, audio) ne sont pas anonymisés.
