---
title: Aegra — Privacy-first LLM agent framework
---

# Aegra

**Aegra** est un framework d'agent LLM conçu pour protéger les données personnelles (PII) de vos utilisateurs sans compromettre les capacités du modèle.

## Principe fondamental

Le LLM ne voit jamais les vraies valeurs. Il travaille uniquement avec des **jetons opaques** (`<PERSON:a1b2c3d4>`, `<LOCATION:e5f6a7b8>`) qui sont :

- **générés de façon déterministe** — la même valeur produit toujours le même jeton, à travers tous les tours de conversation ;
- **transparents pour les outils** — le middleware désanonymise les arguments avant l'exécution, puis réanonymise le résultat avant que le modèle ne le lise ;
- **restitués automatiquement** — la réponse finale est désanonymisée avant d'être renvoyée à l'utilisateur.

## Architecture en un coup d'œil

```
Utilisateur → [Middleware before_model] → LLM → [Middleware wrap_tool_call] → Outil
                                                  ↑                              ↓
                                          [Middleware after_agent]        résultat brut
                                                  ↓
                                              Utilisateur
```

## Composants principaux

| Module | Rôle |
|--------|------|
| [`anonymizer.py`](anonymizer.md) | Détection NER (GLiNER2), remplacement par placeholders, cohérence multi-tours |
| [`middleware.py`](middleware.md) | Hooks LangGraph (`before_model`, `wrap_tool_call`, `after_agent`) |
| [`ttl_sweeper.py`](configuration.md#ttl-sweeper) | Suppression automatique des threads expirés |

## Stack technique

- **LangGraph** + **LangChain** — orchestration de l'agent
- **GLiNER2** (`fastino/gliner2-large-v1`) — NER zero-shot multilingue
- **Python 3.12+** — requis par les dépendances

## Pour commencer

```bash
git clone <repo>
cd aegra
uv sync
uv run python -m maskara.app
```

Consultez le [Guide de démarrage](getting-started.md) pour les détails d'installation et de configuration.
