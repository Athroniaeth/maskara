---
title: Middleware Reference API
---

# Middleware

`src/maskara/middleware.py`

Le middleware d'anonymisation PII s'integre dans LangGraph via le systeme de hooks `AgentMiddleware`. Il intercepte les communications entre l'utilisateur, le LLM et les outils pour garantir qu'aucune donnee personnelle ne transite vers le modele.

Contrairement a l'`Anonymizer` (qui utilise des jetons `<TYPE_N>`), le middleware utilise des **jetons bases sur un hash SHA-256** (`<TYPE:xxxxxxxx>`). Le mapping est persiste dans le state LangGraph et survit aux redemarrages du serveur.

---

## `PIIState`

```python
class PIIState(AgentState):
    pii_to_token: Annotated[dict[str, str], _merge_dicts]
    pii_to_original: Annotated[dict[str, str], _merge_dicts]
```

Extension de `AgentState` qui persiste le mapping bidirectionnel PII ↔ jetons dans le checkpoint LangGraph.

| Champ | Exemple |
|-------|---------|
| `pii_to_token` | `{"Lyon": "<LOCATION:e5f6a7b8>", "Tim Cook": "<PERSON:a1b2c3d4>"}` |
| `pii_to_original` | `{"<LOCATION:e5f6a7b8>": "Lyon", "<PERSON:a1b2c3d4>": "Tim Cook"}` |

Ce state est checkpointe par LangGraph, ce qui garantit la coherence des jetons meme apres redemarrage du serveur.

---

## Format des jetons

```
<ENTITY_TYPE:xxxxxxxx>
```

- `ENTITY_TYPE` : `PERSON`, `LOCATION`, `ORGANIZATION`, `EMAIL_ADDRESS`, `PHONE_NUMBER`
- `xxxxxxxx` : 8 premiers caracteres hexadecimaux du SHA-256 de la valeur originale

Le hash est **deterministe** : `"Lyon"` produit toujours le meme jeton, quel que soit le thread ou la session. Cela simplifie la gestion de la coherence pas besoin de thread store.

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

| Parametre | Defaut | Description |
|-----------|--------|-------------|
| `analyzed_fields` | `["PERSON", "LOCATION", "ORGANIZATION", "EMAIL_ADDRESS", "PHONE_NUMBER"]` | Types d'entites a anonymiser |
| `gliner_model` | `"fastino/gliner2-large-v1"` | Modele HuggingFace GLiNER2 |
| `threshold` | `0.4` | Score de confiance minimum |
| `language` | `"fr"` | Code langue passe au modele NER |

### Ajustement du seuil

| Valeur | Comportement |
|--------|-------------|
| `0.3` | Permissif detecte beaucoup, risque de faux positifs |
| `0.4` | Defaut bon equilibre precision/rappel |
| `0.6` | Conservateur seulement les entites tres claires |

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

Le middleware intervient a trois moments du cycle de vie d'un appel agent :

### `before_model(state, runtime)`

Execute **avant chaque appel LLM**. Traite les messages dans cet ordre :

1. **`AIMessage`s** : re-applique les mappings connus (step-1 only, sans GLiNER2) pour restaurer l'anonymisation apres `after_agent`
2. **Dernier `HumanMessage`** : anonymisation complete via GLiNER2
3. **`ToolMessage`s apres le dernier `AIMessage`** : anonymisation complete (les resultats d'outils sont stockes bruts par `wrap_tool_call`)

**Retourne :** patch d'etat avec les messages mis a jour et les nouvelles entrees de mapping, ou `None`.

**Pourquoi les `AIMessage`s sont re-anonymises sans GLiNER2 ?** Parce que `after_agent` desanonymise la reponse finale pour l'utilisateur. Quand le LLM revoit cette reponse dans l'historique au tour suivant, il faut la re-anonymiser. Mais on ne lance pas GLiNER2 dessus on re-applique simplement les mappings connus via `str.replace`, ce qui est plus rapide et ne risque pas de detecter de faux positifs dans du texte genere.

---

### `wrap_tool_call(request, handler)`

Execute **autour de chaque appel d'outil** :

1. Desanonymise les arguments de l'outil (les chaines `str` uniquement)
2. Execute l'outil avec les vraies valeurs
3. Retourne le resultat **brut** (non anonymise)

Le resultat brut est intentionnel : `before_model` l'anonymisera au tour suivant avant que le LLM ne le lise. Cela evite un double passage GLiNER2 inutile.

---

### `after_agent(state, runtime)`

Execute **apres la reponse finale de l'agent**. Desanonymise le dernier `AIMessage` pour que l'utilisateur recoive les vraies valeurs.

---

## Pipeline d'anonymisation du middleware

Le middleware a une logique d'anonymisation legerement differente de l'`Anonymizer` :

```
1. Remplace les valeurs deja connues (cache _to_token)
2. Masque les jetons existants avec des null-bytes
   → empeche GLiNER de re-detecter le contenu d'un jeton
3. Lance GLiNER2 sur le texte masque
4. Cree ou reutilise un jeton hash pour chaque nouvelle entite
5. Restaure les jetons masques
```

L'etape 2 (masquage null-byte) est specifique au middleware. Elle empeche la creation de jetons imbriques par exemple si le texte contient deja `<PERSON:a1b2c3d4>`, GLiNER pourrait detecter "PERSON" comme entite. Le masquage evite ca.

---

## Entites supportees

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
    return f"Email envoye a {to}."


middleware = PIIAnonymizationMiddleware(threshold=0.4, language="fr")

graph = create_agent(
    model="openai:gpt-4o",
    state_schema=PIIState,
    tools=[send_email],
    middleware=[middleware],
)

result = graph.invoke(
    {
        "messages": [{
            "role": "user",
            "content": "Envoie un email a pierre@example.com pour lui souhaiter bon anniversaire.",
        }]
    },
    config={"configurable": {"thread_id": "session-abc"}},
)

# La reponse finale est desanonymisee automatiquement
print(result["messages"][-1].content)
# "J'ai envoye un email a pierre@example.com pour lui souhaiter bon anniversaire."
```
