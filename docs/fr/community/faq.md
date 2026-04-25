---
icon: lucide/message-circle-question
---

# FAQ

??? question "Est-ce vraiment utile d'anonymiser les PII avant d'appeler un LLM ?"
    Oui, et ce indépendamment de `piighost`. Les enjeux (exfiltration vers les providers, réquisition légale, entraînement sur les conversations, conformité RGPD, fuites via RAG et outils) sont détaillés dans [Pourquoi anonymiser ?](../why-anonymize.md). La page est agnostique à la librairie : elle explique pourquoi le problème existe avant de justifier une solution comme `piighost`.

??? question "Mes placeholders doivent-ils avoir ce format `<<PERSON_1>>` ?"
    Non. Le format est piloté par `AnyPlaceholderFactory`. Par défaut `CounterPlaceholderFactory` produit `<<LABEL_N>>`, mais `LabeledHashPlaceholderFactory` produit `<<LABEL:hash>>`, `RedactPlaceholderFactory` produit `<<LABEL>>` sans compteur, et vous pouvez écrire votre propre factory. Voir [Placeholder factories](../placeholder-factories.md).

??? question "Le LLM voit-il les vraies PII quand il appelle un outil ?"
    Non. Le middleware désanonymise les arguments juste avant l'exécution de l'outil, puis réanonymise la réponse avant qu'elle ne retourne au LLM. L'outil voit les vraies valeurs, le LLM ne voit que les placeholders. Voir le diagramme dans [Architecture](../architecture.md).

??? question "Comment contrôler ce que voit un outil : placeholder ou vraie valeur ?"
    Le paramètre `tool_strategy` de `PIIAnonymizationMiddleware` expose trois modes (`FULL`, `INBOUND_ONLY`, `PASSTHROUGH`) via l'enum `ToolCallStrategy`. Le bon choix dépend de la possibilité que l'outil émette de nouvelles PII et du niveau de cloisonnement souhaité. Voir [Stratégies d'appel outil](../tool-call-strategies.md) pour les compromis et l'arbre de décision, et [Placeholder factories](../placeholder-factories.md) pour la contrainte de factory qui force `PreservesIdentity` dans tous les modes sauf `PASSTHROUGH`.

??? question "Que se passe-t-il si le LLM hallucine une PII qui n'était pas dans l'entrée ?"
    Elle n'est **pas** anonymisée par `piighost` : l'entity linking travaille sur les détections issues de l'entrée, pas sur des valeurs inventées. Pour couvrir ce cas, ajoutez une passe de détection sur la sortie du LLM au niveau applicatif. Voir [Limites](../limitations.md).

??? question "Le cache est-il partagé entre threads ou conversations ?"
    Non. Le cache `aiocache` est scopé par `thread_id`. Deux conversations parallèles ne voient pas les placeholders l'une de l'autre, ce qui évite les fuites latérales entre utilisateurs. Le `thread_id` est extrait automatiquement de la config LangGraph.

??? question "Puis-je utiliser `piighost` sans LangChain ?"
    Oui. `AnonymizationPipeline` et `ThreadAnonymizationPipeline` sont utilisables seuls, sans middleware. Voir [Usage basique](../examples/basic.md).

??? question "`piighost` chiffre-t-il les données en cache ?"
    Non. Le cache stocke le mapping `placeholder → valeur` en mémoire (ou dans le backend `aiocache` configuré). Voir [Sécurité](../security.md) pour la liste exhaustive de ce qui est hors périmètre.
