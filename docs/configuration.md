---
title: Configuration
---

# Configuration

## Variables d'environnement (`.env`)

Aegra charge automatiquement le fichier `.env` au démarrage via `python-dotenv`.

### Variables LLM

| Variable | Description | Exemple |
|----------|-------------|---------|
| `OPENAI_API_KEY` | Clé API OpenAI | `sk-...` |
| `ANTHROPIC_API_KEY` | Clé API Anthropic (si modèle Claude) | `sk-ant-...` |

### Variables Langfuse (tracing, optionnel)

| Variable | Description | Défaut |
|----------|-------------|--------|
| `LANGFUSE_PUBLIC_KEY` | Clé publique Langfuse | — |
| `LANGFUSE_SECRET_KEY` | Clé secrète Langfuse | — |
| `LANGFUSE_HOST` | URL de l'instance Langfuse | `https://cloud.langfuse.com` |

### Variables Aegra

| Variable | Description | Défaut |
|----------|-------------|--------|
| `AEGRA_CONFIG` | Chemin vers le fichier de config JSON | `""` (cherche `aegra.json` puis `langgraph.json`) |

---

## Fichier `aegra.json`

Fichier de configuration principal pour les paramètres serveur et le TTL sweeper. Placé à la racine du projet.

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

### Section `checkpointer.ttl`

| Clé | Type | Description |
|-----|------|-------------|
| `strategy` | `"delete"` | Stratégie de nettoyage (seule valeur supportée) |
| `sweep_interval_minutes` | `int` | Fréquence du balayage en minutes |
| `default_ttl` | `int` | Durée de vie maximale d'un thread en minutes |

!!! example "Exemple : sessions de 24h, balayage toutes les heures"
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

!!! example "Exemple : sessions courtes (1h), balayage fréquent"
    ```json
    {
      "checkpointer": {
        "ttl": {
          "strategy": "delete",
          "sweep_interval_minutes": 5,
          "default_ttl": 60
        }
      }
    }
    ```

---

## TTL Sweeper

`src/aegra/ttl_sweeper.py`

Le TTL sweeper est un processus asyncio qui supprime automatiquement les threads LangGraph expirés. Il fonctionne en arrière-plan et utilise le [LangGraph SDK](https://langchain-ai.github.io/langgraph/cloud/reference/sdk/python_sdk_ref/) pour lister et supprimer les threads.

### Fonctionnement

```
Démarrage → attente 5s (serveur prêt) → boucle infinie :
  1. Chercher tous les threads (pagination par 100)
  2. Comparer created_at / updated_at avec cutoff = now - default_ttl
  3. Supprimer les threads expirés
  4. Attendre sweep_interval_minutes
```

### API

#### `load_ttl_config()`

```python
def load_ttl_config() -> dict | None
```

Charge la configuration TTL depuis `aegra.json` ou `langgraph.json`. Le chemin peut être surchargé via `AEGRA_CONFIG`.

**Retourne :** Dict avec les clés `strategy`, `sweep_interval_minutes`, `default_ttl`, ou `None` si aucune config trouvée.

---

#### `sweep_expired_threads(base_url, default_ttl_minutes)`

```python
async def sweep_expired_threads(base_url: str, default_ttl_minutes: int) -> None
```

Supprime tous les threads plus anciens que `default_ttl_minutes` via le LangGraph SDK.

| Paramètre | Description |
|-----------|-------------|
| `base_url` | URL du serveur Aegra (ex: `http://localhost:8000`) |
| `default_ttl_minutes` | Âge maximum d'un thread avant suppression |

---

#### `run_sweeper(base_url, sweep_interval_minutes, default_ttl_minutes)`

```python
async def run_sweeper(
    base_url: str,
    sweep_interval_minutes: int,
    default_ttl_minutes: int,
) -> None
```

Lance la boucle du sweeper en tant que tâche asyncio indéfinie.

---

### Intégration dans l'application

```python
import asyncio
from maskara.ttl_sweeper import load_ttl_config, run_sweeper


async def main():
    ttl_config = load_ttl_config()
    if ttl_config:
        asyncio.create_task(run_sweeper(
            base_url="http://localhost:8000",
            sweep_interval_minutes=ttl_config["sweep_interval_minutes"],
            default_ttl_minutes=ttl_config["default_ttl"],
        ))
    # ... démarrage du serveur ...
```

---

## Modèle LLM

Le modèle est configuré directement dans `graph.py` via la syntaxe `provider:model-id` de LangChain :

```python
graph = create_agent(
    model="openai:gpt-4o",        # OpenAI GPT-4o
    # model="anthropic:claude-3-5-sonnet-20241022",  # Anthropic Claude
    ...
)
```

### Modèles GLiNER2

| Modèle | Taille | Usage recommandé |
|--------|--------|-----------------|
| `fastino/gliner2-base-v1` | ~180M | Développement, tests |
| `fastino/gliner2-large-v1` | ~350M | Production (défaut middleware) |

Le modèle large offre une meilleure précision, surtout pour les entités rares et les textes courts.

---

## `PIIAnonymizationMiddleware` — Paramètres avancés

```python
PIIAnonymizationMiddleware(
    analyzed_fields=["PERSON", "EMAIL_ADDRESS"],  # Restreindre les types détectés
    gliner_model="fastino/gliner2-large-v1",
    threshold=0.35,   # Plus bas = plus de rappel
    language="fr",
)
```

### Ajustement du seuil `threshold`

| Valeur | Comportement |
|--------|-------------|
| `0.3` | Très permissif — détecte beaucoup, risque de faux positifs |
| `0.4` | Défaut — bon équilibre précision/rappel |
| `0.6` | Conservateur — seulement les entités très claires |

!!! warning
    Un seuil trop bas peut anonymiser des mots non-PII, rendant les réponses du LLM confuses.
