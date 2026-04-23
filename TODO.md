# TODO

Pistes d'amélioration identifiées lors de l'audit des écarts objectifs
vs implémentation. Les trois items P0 sont déjà traités sur cette
branche ; ce fichier suit le reste.

## P1 — Importants

### Tests middleware : edge cases manquants

Couvrir dans `tests/test_middleware.py` :

- `ToolMessage` déjà anonymisé (ne doit pas être ré-encodé par
  `abefore_model`).
- Fallback `CacheMissError` dans `aafter_model` : ce chemin (code
  autour de `middleware.py` ~L150) n'a aucun test.
- Hallucinations PII du LLM : le LLM génère une valeur qui n'a jamais
  été dans l'entrée. `piighost` ne peut pas la lier puisqu'elle n'a
  jamais été mise en cache. Vérifier le comportement observable (pas
  d'exception, PII hallucinée sortie telle quelle côté utilisateur).

Effort estimé : ~3h.

## P2 — Documentation / hygiène

### Doc cache Redis en production

Ajouter dans `docs/{en,fr}/deployment.md` un encadré expliquant :

- Le cache `aiocache` in-memory par défaut n'est pensé que pour le dev
  ou un déploiement mono-process.
- En multi-worker, chaque process a son propre espace de placeholders
  pour le même `thread_id` → incohérences ou déanonymisation cassée.
- Exemple `aiocache.RedisCache` prêt à copier-coller (serializer, prefix,
  TTL).

Effort : ~30 min.

### Doc sécurité placeholders

Dans `docs/{en,fr}/security.md`, ajouter une section sur le risque
rainbow tables avec `HashPlaceholderFactory` (SHA-256 déterministe sur
un petit espace comme prénoms/villes). Recommander :

- Un salt au niveau de la factory.
- Ou `CounterPlaceholderFactory` quand la déterministe-ité inter-messages
  n'est pas requise.

Effort : ~1h.

### Cohérence docs Aegra / Langfuse

Les sections Aegra et Langfuse ont été retirées de la doc principale
(commit `09dc958`) mais `examples/graph/README.md` et `CLAUDE.md`
continuent de les citer. À aligner :

- Soit restaurer un pointeur depuis `getting-started.md` vers
  `examples/graph/` pour le stack complet.
- Soit purger les mentions dans `CLAUDE.md` et
  `examples/graph/README.md`.

Effort : ~1h.

## P3 — Nice-to-have

### Formats structurés (PDF / DOCX / CSV / JSON)

Cas d'usage RGPD batch : ETL d'anonymisation sur des documents
structurés. Actuellement, le seul point d'entrée prend du texte brut.

- PDF : `pypdf` pour extraction, challenge de la reconstruction.
- DOCX : `python-docx`, plus simple (XML structuré).
- CSV : trivial (anonymise par cellule configurable par colonne).
- JSON : trivial (anonymise les valeurs `str`, récursif sur dicts).

Effort : ~2 jours. Décider d'abord si c'est dans le scope de la
librairie ou d'un package séparé (`piighost-formats`).

### ROADMAP + comparatif + parité FR/EN

- `ROADMAP.md` à la racine : jalons jusqu'à v1.0 (P0/P1 actuels + ce
  qui reste).
- Tableau comparatif vs Presidio / dataFog / pii-guard dans le README
  principal. Différenciateurs à mettre en avant : middleware natif
  LangChain, cross-message linking, packs regex + validateurs
  shippés.
- Audit de parité FR/EN : vérifier que les dernières mises à jour
  (notamment les diagrammes Mermaid de `architecture.md`) sont bien
  reflétées côté FR.

Effort : ~2h.

## Hors scope (exclu explicitement)

Ces items apparaissaient dans l'audit initial mais ont été écartés
par l'utilisateur :

- Finaliser `feat/chunking-benchmark` (branche laissée telle quelle).
- Support du streaming middleware.
- API REST standalone ou CLI `piighost anonymize`.
- Logging structuré / métriques Prometheus / OTEL tracing.
- Helper dédié Redis/Memcached (remplacé par de la doc, voir P2).
- Mécanisme `languages=[...]` sur les regex (remplacé par les packs
  par pays, déjà livrés).
