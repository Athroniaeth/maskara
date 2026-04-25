---
icon: lucide/list-checks
---

# Roadmap

Cette page liste les améliorations envisagées pour PIIGhost. Les items
sont regroupés par thème ; une case cochée signifie que l'item a été
livré.

!!! note "Comment lire cette page"
    Cette roadmap n'est pas un engagement de calendrier. Elle reflète
    les pistes d'évolution identifiées et leur état d'avancement.

## Sécurité du mapping (placeholder ↔ PII)

Le mapping `placeholder ↔ PII` est aujourd'hui conservé en clair dans
le backend `aiocache` configuré. Les chantiers ci-dessous renforcent
les garanties offertes lorsque le backend lui-même est compromis.

- [ ] **Sel et poivre sur le hash des placeholders.** Aujourd'hui,
  `LabelHashPlaceholderFactory` et `FakerHashPlaceholderFactory`
  dérivent un SHA-256 déterministe de la PII. Sur un espace de
  valeurs réduit (prénoms, villes), un attaquant peut reconstruire la
  table inverse via des rainbow tables. Ajouter un sel par instance
  et un poivre global rendrait la dérivation non rejouable hors du
  processus.

- [ ] **Backend SQLAlchemy (aiosqlite + PostgreSQL).** Le cache par
  défaut est in-memory et lié au processus. Un backend SQLAlchemy
  apporterait :
    - une persistance simple en dev via `aiosqlite` ;
    - un partage multi-worker en production via PostgreSQL ;
    - une cohérence stricte du `thread_id` à travers les workers.

- [ ] **Chiffrement du mapping au repos.** Inspiré du `PostgresStore`
  de LangChain, l'idée est de chiffrer le mapping côté librairie
  avant de le confier au backend. En cas de fuite de la base ou du
  cache, un attaquant qui n'a pas la clé ne récupère aucune PII. À
  étudier : faisabilité, modèle de gestion de clé (variable d'env,
  KMS, rotation), impact sur les performances.

## Voir aussi

- [Sécurité](security.md) : modèle de menace actuel et garanties.
- [Déploiement](deployment.md) : configuration du cache en production.
