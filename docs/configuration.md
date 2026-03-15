---
title: Configuration
---

# Configuration

## Variables d'environnement (`.env`)

Maskara charge automatiquement le fichier `.env` au demarrage via `python-dotenv`.

### Application

| Variable | Description | Defaut |
|----------|-------------|--------|
| `PROJECT_NAME` | Nom du projet | `maskara` |
| `DEBUG` | Mode debug | `true` |
| `HOST` | Adresse d'ecoute | `0.0.0.0` |
| `PORT` | Port du serveur | `8000` |
| `AUTH_TYPE` | Type d'authentification (`noop`, `custom`) | `noop` |

### Base de donnees

| Variable | Description | Defaut |
|----------|-------------|--------|
| `DATABASE_URL` | URL de connexion complete (prioritaire) | |
| `POSTGRES_USER` | Utilisateur PostgreSQL | `maskara` |
| `POSTGRES_PASSWORD` | Mot de passe | `maskara_secret` |
| `POSTGRES_DB` | Nom de la base | `maskara` |
| `POSTGRES_HOST` | Hote | `localhost` |
| `POSTGRES_PORT` | Port | `5432` |
| `DB_ECHO_LOG` | Log des requetes SQL | `false` |

Si `DATABASE_URL` est defini, les variables `POSTGRES_*` individuelles sont ignorees.

### Pools de connexions

| Variable | Description | Defaut |
|----------|-------------|--------|
| `SQLALCHEMY_POOL_SIZE` | Taille du pool SQLAlchemy | `2` |
| `SQLALCHEMY_MAX_OVERFLOW` | Connexions supplementaires autorisees | `0` |
| `LANGGRAPH_MIN_POOL_SIZE` | Pool minimum LangGraph | `1` |
| `LANGGRAPH_MAX_POOL_SIZE` | Pool maximum LangGraph | `6` |

### LLM

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | Cle API OpenAI |
| `ANTHROPIC_API_KEY` | Cle API Anthropic (optionnel) |

### Observabilite (OpenTelemetry)

| Variable | Description | Defaut |
|----------|-------------|--------|
| `OTEL_SERVICE_NAME` | Nom du service | `maskara-backend` |
| `OTEL_TARGETS` | Cibles de tracing (`LANGFUSE,PHOENIX,GENERIC`) | `""` (desactive) |
| `OTEL_CONSOLE_EXPORT` | Export vers stdout | `false` |

### Langfuse

| Variable | Description |
|----------|-------------|
| `LANGFUSE_BASE_URL` | URL de l'instance Langfuse |
| `LANGFUSE_PUBLIC_KEY` | Cle publique |
| `LANGFUSE_SECRET_KEY` | Cle secrete |

### Authentification API

| Variable | Description |
|----------|-------------|
| `SECRET_PEPPER` | Pepper pour le hachage Argon2 des cles API |
| `API_KEY_DEV` | Cle API de developpement |

---

## Fichier `maskara.json`

Fichier de configuration pour le TTL sweeper. Place a la racine du projet.

```json
{
  "name": "maskara",
  "graphs": {
    "agent": "./src/maskara/graph.py:graph"
  },
  "http": {
    "app": "./src/maskara/app.py:app"
  },
  "checkpointer": {
    "ttl": {
      "strategy": "delete",
      "sweep_interval_minutes": 60,
      "default_ttl": 20160
    }
  }
}
```

Le chemin du fichier peut etre surcharge via la variable `AEGRA_CONFIG`. Par defaut, Maskara cherche `aegra.json` puis `langgraph.json`.

### Section `checkpointer.ttl`

| Cle | Type | Description |
|-----|------|-------------|
| `strategy` | `"delete"` | Strategie de nettoyage (seule valeur supportee) |
| `sweep_interval_minutes` | `int` | Frequence du balayage en minutes |
| `default_ttl` | `int` | Duree de vie maximale d'un thread en minutes |

---

## TTL Sweeper

`src/maskara/ttl_sweeper.py`

Le TTL sweeper est un processus asyncio qui supprime automatiquement les threads LangGraph expires. Il fonctionne en arriere-plan via le LangGraph SDK.

### Fonctionnement

```
Demarrage → attente 5s (serveur pret) → boucle infinie :
  1. Lister tous les threads (pagination par 100)
  2. Comparer created_at / updated_at avec cutoff = now - default_ttl
  3. Supprimer les threads expires
  4. Attendre sweep_interval_minutes
```

### API

#### `load_ttl_config()`

```python
def load_ttl_config() -> dict | None
```

Charge la configuration TTL depuis le fichier de config. Retourne les cles `strategy`, `sweep_interval_minutes`, `default_ttl`, ou `None` si aucune config trouvee.

#### `sweep_expired_threads(base_url, default_ttl_minutes)`

```python
async def sweep_expired_threads(base_url: str, default_ttl_minutes: int) -> None
```

Supprime tous les threads plus anciens que `default_ttl_minutes`.

#### `run_sweeper(base_url, sweep_interval_minutes, default_ttl_minutes)`

```python
async def run_sweeper(
    base_url: str,
    sweep_interval_minutes: int,
    default_ttl_minutes: int,
) -> None
```

Lance la boucle du sweeper en tant que tache asyncio indefinie.

---

## Modeles GLiNER2

| Modele | Taille | Usage |
|--------|--------|-------|
| `fastino/gliner2-base-v1` | ~180M | Developpement, tests |
| `fastino/gliner2-large-v1` | ~350M | Production (defaut du middleware) |

Le modele large offre une meilleure precision pour les entites rares et les textes courts.

---

## Modele LLM

Configure dans `graph.py` via la syntaxe `provider:model-id` de LangChain :

```python
graph = create_agent(
    model="openai:gpt-4o",
    # model="anthropic:claude-sonnet-4-20250514",
    ...
)
```
