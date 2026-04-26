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

## Garde-fous pour le déploiement multi-instance

Le cache par défaut (`SimpleMemoryCache`) est in-memory et lié au
processus. C'est un excellent défaut pour le développement et les
déploiements single-instance, mais en multi-instance derrière un load
balancer, les mappings `placeholder ↔ PII` ne sont pas partagés : un
même `thread_id` routé vers deux workers verra Patrick assigné à
`<<PERSON:1>>` au tour 1 puis `<<PERSON:2>>` au tour 2, cassant la
cohérence du placeholder en pleine conversation.

- [ ] **Warning à la première instanciation sans backend explicite.**
  Émettre un `PIIGhostConfigWarning` (catégorie custom, filtrable via
  `warnings.filterwarnings`) une seule fois par processus quand
  `ThreadAnonymizationPipeline` est créé sans backend partagé. Le
  message doit parler de **correctness** (cohérence des placeholders
  cross-worker) et pas seulement de performance, pour que
  l'utilisateur comprenne le vrai risque.

- [ ] **Page « Déploiement multi-instance » dans la doc.** Une section
  dédiée qui explique le piège, montre le warning, et donne un exemple
  Redis copy-pasteable. À aligner sur la formulation de LangGraph
  (`MemorySaver` vs `PostgresSaver` / `RedisSaver`) pour parler
  immédiatement au public LangChain.

## Validation post-anonymisation

Aujourd'hui, rien ne garantit en sortie de pipeline que le texte
anonymisé ne contient plus de PII détectable : un détecteur mal
configuré, une entité ratée par le NER, un placeholder qui n'a pas
matché peuvent laisser fuiter des données. Les protocoles ci-dessous
ajoutent un filet de sécurité optionnel en fin de pipeline.

- [ ] **Protocole `AnyGuardRail` et implémentations.** Étage final
  binaire qui rejoue une détection (regex stricte, LLM, ou n'importe
  quel `AnyDetector`) sur le texte anonymisé et lève une
  `PIIRemainingError` si quelque chose est encore identifié. API
  minimale, pas de seuil à régler. Implémentations prévues :
  `DetectorGuardRail` (réutilise un `AnyDetector` quelconque),
  `LLMGuardRail` (petit LLM local), et `DisabledGuardRail` par défaut
  pour rester cohérent avec les autres étages du pipeline.

- [ ] **Protocole `AnyRiskAssessor` et implémentations.** Étage
  optionnel qui retourne un score continu de risque de
  ré-identification (`0.0` à `1.0`) sans agir lui-même : l'utilisateur
  décide quoi faire du score (logger, bloquer, relancer le pipeline
  avec une politique plus stricte). Plus complexe que `GuardRail` car
  il nécessite de calibrer un seuil. À viser après le `GuardRail`
  pour les cas d'usage haute valeur (médical, juridique, conseil
  financier) où le binaire pass/fail est insuffisant. Utilisable au
  runtime ou hors-ligne, à la discrétion de l'utilisateur.

## Détection

PIIGhost orchestre des détecteurs sans en imposer un en particulier.
Les pistes ci-dessous renforcent la qualité et la mesurabilité de
l'étape de détection.

- [ ] **Benchmarks publics du pipeline.** Mesurer l'overhead de
  PIIGhost lui-même (et non du NER sous-jacent) sur un corpus
  reproductible : latence par étage, throughput selon le nombre
  d'entités, impact du cache (hit / miss ratio), p50 / p95 / p99 sur
  un setup détecteur de référence. Le but est de donner aux
  utilisateurs une base de chiffres pour calibrer leurs SLA et de
  détecter les régressions de performance entre versions.

- [ ] **Renforcement du `LLMDetector`.** Le `LLMDetector` actuel
  détecte des PII via prompt LLM. Pistes d'amélioration : support des
  LLM locaux (Ollama, llama.cpp, vLLM) pour réduire le coût et garder
  les données en interne ; sortie structurée stricte (JSON Schema,
  Pydantic) pour fiabiliser le parsing ; rôle de désambiguateur dans
  un `CompositeDetector` (un autre détecteur propose des candidats,
  le LLM filtre les faux positifs comme « Rose » prénom vs fleur en
  s'appuyant sur le contexte). Le contexte global du LLM résout
  exactement les limites des NER spécialisés.

## Stratégies d'anonymisation

L'anonymisation actuelle est binaire (placeholder ou valeur claire).
Les pistes ci-dessous ouvrent des comportements intermédiaires
adaptés à des cas d'usage spécifiques.

- [ ] **Politiques de déanonymisation différenciées.** Trois variantes
  utiles, sélectionnables par label via un protocole
  `AnyDeanonymizationPolicy` (avec `IdentityPolicy` par défaut) :
    - **Pseudonymisation persistante** : au lieu de `<<PERSON:1>>`,
      retourner un nom Faker stable cross-thread (Patrick → « Alex
      Martin » toujours). Permet aux équipes data / analytics
      d'agréger des conversations sans manipuler de PII réelles.
    - **k-anonymity sur les valeurs sensibles** : pour les attributs
      numériques ou catégoriels (âge, code postal, salaire),
      retourner une tranche au lieu de la valeur exacte : `34` →
      `30-39`, `75001` → `Paris`, `52340 €` → `[50k-60k]`.
    - **Differential privacy** : pour les valeurs numériques exposées
      à un LLM qui pourrait les agréger, ajouter un bruit calibré
      (Laplace, gaussien). Cas d'usage : reporting agrégé où la
      valeur exacte d'un individu n'est pas nécessaire.

- [ ] **`ToolPIIPolicy` : politique fine par appel d'outil.**
  Aujourd'hui, `awrap_tool_call` déanonymise tous les arguments
  d'outil avant exécution puis ré-anonymise le résultat. C'est
  binaire et global. Une politique déclarative par tool ouvrirait
  des architectures zero-trust plus fines :
    - *Whitelist d'attributs* : ce tool reçoit `name` et `email`,
      mais pas `phone`.
    - *Pseudonymisation par tool* : ce tool reçoit une valeur Faker
      stable plutôt que la vraie (utile pour des CRM externes où on
      veut une trace stable sans exposer le client réel).
    - *Politique de résultat* : ce tool peut retourner du contenu en
      clair (résumé public) sans repasser par la détection.

  L'API ressemblerait à un argument du middleware :
  `PIIAnonymizationMiddleware(tool_policies={"send_email":
  ToolPolicy(reveal=["email"], hide=["phone"])})`.

## Intégrations

- [ ] **Adapters au-delà de LangChain.** La logique du middleware
  (anonymisation avant LLM, déanonymisation pour l'utilisateur, wrap
  des appels d'outils) est isomorphe entre frameworks. Cibles :
    - **LlamaIndex** : intégration via les agent hooks.
    - **OpenAI Agents SDK** : hooks `on_message_start` /
      `on_tool_call`.
    - **Anthropic SDK natif** : intercepteur sur `messages.create`
      avec gestion du `tool_use`.
    - **Pydantic AI** : middleware compatible avec leur graph
      runtime.
    - **DSPy** : module wrapper pour les pipelines.
    - **Mode « proxy HTTP transparent »** : intercepteur générique
      côté requête / réponse (httpx middleware, ou serveur proxy)
      pour les agents qui n'utilisent aucun de ces frameworks.

  Le cœur (`AnonymizationPipeline`, `ConversationMemory`) reste
  identique, seule la couche de glue change. À mutualiser dans un
  package séparé ou via des extras (`piighost[llamaindex]`,
  `piighost[openai]`, etc.).

## Observabilité et progressive rollout

- [ ] **Mode « shadow ».** Middleware en lecture seule qui logge ce
  qu'il *aurait* anonymisé sans modifier les messages. Permet
  d'intégrer PIIGhost dans un agent en prod sans risque pendant la
  phase de calibration (ajustement des labels, du seuil de confiance,
  des détecteurs). Implémentation phasée :
    - *Phase 1 : intégration Langfuse.* Logger chaque détection en
      trace Langfuse avec score, label, position (sans la valeur
      claire), et le placeholder qui aurait été appliqué. Permet de
      visualiser sur un dashboard ce que le pipeline ferait sans
      affecter l'agent.
    - *Phase 2 : système d'alerte (optionnel).* Au-delà d'un seuil
      configurable de PII détectées par conversation, déclencher une
      alerte (webhook, Slack, email) pour intervention humaine.
      Utile dans les environnements régulés ou pour valider qu'un
      nouveau détecteur n'introduit pas de régression silencieuse.

- [ ] **Audit trail structuré pour la conformité.** Logger sans
  valeurs PII brutes qui trace par message : nombre de PII détectées,
  distribution par label, détecteur source, score de confiance, hash
  de la valeur (pour corréler sans révéler). Différent du mode shadow
  car ce log tourne en **runtime de production**, pas en passif.
    - Format structuré (JSON Lines, spans OpenTelemetry) pour
      ingestion par n'importe quel SIEM ou plateforme observability.
    - Hash déterministe par PII pour permettre des analyses agrégées
      (« le terme X apparaît 47 fois ce mois ») sans stocker la
      valeur.
    - Couplage avec les traces Langfuse du mode shadow pour avoir
      une vue end-to-end.
    - Export « DPIA snippet » : générer automatiquement les flux de
      données pour les audits RGPD article 35.

## Évaluation de robustesse

- [ ] **Évaluation contradictoire intégrée (exploratoire, priorité
  basse).** Mode « red team » qui prend une conversation anonymisée
  et tente activement de ré-identifier la personne (via prompting
  d'un LLM adverse, ou via heuristiques de cross-referencing entre
  quasi-identifiants). Donne un score de robustesse mesuré plutôt
  qu'une promesse théorique.

  L'utilité pratique reste à valider : le `RiskAssessor` (prévu dans
  « Validation post-anonymisation » plus haut) couvre une grande
  partie du besoin avec un seul appel LLM, alors que l'évaluation
  contradictoire demande plusieurs passes adverses, donc nettement
  plus coûteuse pour un gain marginal. À considérer uniquement pour
  les audits ponctuels de conformité ou les benchmarks publics, pas
  pour un usage runtime.

## Voir aussi

- [Sécurité](security.md) : modèle de menace actuel et garanties.
- [Déploiement](deployment.md) : configuration du cache en production.
