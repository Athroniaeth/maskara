---
title: Maskara Anonymisation PII pour agents LLM
---

# Maskara

Maskara est une couche d'anonymisation qui s'intercale entre l'utilisateur et un LLM. Son rôle : détecter les données personnelles (noms, lieux, entreprises, produits) dans les messages entrants, les remplacer par des jetons opaques (`<PERSON_1>`, `<LOCATION_2>`), puis restituer les vraies valeurs dans la réponse finale.

Le LLM ne voit jamais les données réelles. Il raisonne sur des jetons qu'il traite comme des valeurs normales, y compris quand il appelle des outils.

## Le probleme

Les LLM cloud traitent les requetes sur des serveurs distants. Envoyer `"Pierre Dupont habite au 12 rue de Lyon"` en clair signifie que le fournisseur du modele voit ces informations. Meme avec des politiques de confidentialite strictes, le risque existe fuite, logging, entrainement involontaire.

Maskara resout ce probleme en ne laissant transiter que des jetons anonymes sur le reseau. Les donnees reelles ne quittent jamais le perimetre du serveur d'application.

## Fonctionnement en bref

```
Utilisateur : "Pierre habite a Lyon"
     |
     v
  Anonymizer  ──── GLiNER2 detecte "Pierre" (PERSON) et "Lyon" (LOCATION)
     |               vocab: {"Pierre": "<PERSON_1>", "Lyon": "<LOCATION_1>"}
     v
  LLM recoit : "<PERSON_1> habite a <LOCATION_1>"
     |
     v
  LLM repond : "<PERSON_1> est bien installe a <LOCATION_1>"
     |
     v
  Deanonymizer ── remplace les jetons par les valeurs du vocab
     |
     v
Utilisateur : "Pierre est bien installe a Lyon"
```

Les outils suivent le meme principe : avant l'execution, les arguments sont desanonymises pour que l'outil recoit les vraies valeurs. Le resultat est re-anonymise avant d'etre renvoye au LLM.

## Deux approches disponibles

Maskara propose deux implementations du meme concept, adaptees a des contextes differents :

| | **Anonymizer** | **PIIAnonymizationMiddleware** |
|---|---|---|
| Fichier | `anonymizer.py` | `middleware.py` |
| Format des jetons | `<TYPE_N>` (ex: `<PERSON_1>`) | `<TYPE:hash>` (ex: `<PERSON:a1b2c3d4>`) |
| Persistance | In-memory (`_thread_store`) | LangGraph state + checkpointer |
| Integration | Via `CustomMiddleware` dans `graph.py` | Directement comme `AgentMiddleware` LangGraph |
| Usage typique | Prototypage, controle fin | Production avec LangGraph |

Les deux utilisent **GLiNER2** pour la detection NER zero-shot et partagent la meme logique fondamentale : detecter → remplacer → restituer.

## Stack technique

- **GLiNER2** NER zero-shot multilingue (pas de modele specifique par langue)
- **LangGraph** + **LangChain** orchestration de l'agent
- **FastAPI** serveur HTTP
- **PostgreSQL** (pgvector) persistance des threads et checkpoints
- **Python 3.12+**

## Modules

| Module | Role |
|--------|------|
| [`anonymizer.py`](anonymizer.md) | Pipeline d'anonymisation : detection, assignation, remplacement |
| [`middleware.py`](middleware.md) | Hooks LangGraph pour anonymisation transparente dans le flux agent |
| [`graph.py`](architecture.md) | Exemple d'agent avec anonymisation via `CustomMiddleware` |
| [`ttl_sweeper.py`](configuration.md#ttl-sweeper) | Nettoyage automatique des threads expires |
| [`app.py`](configuration.md) | Serveur FastAPI avec lifespan et authentification API key |
