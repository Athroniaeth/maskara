---
icon: lucide/book-a
---

# Glossaire

Termes clés utilisés dans la documentation `piighost`. Gardez cette page ouverte si vous débutez avec la bibliothèque
ou avec la NER.

PII
:   **P**ersonally **I**dentifiable **I**nformation, en français **d**onnées à caractère **p**ersonnel. Toute donnée
    qui peut identifier une personne : nom, adresse, numéro de téléphone, email, lieu, organisation, numéro de compte.
    `piighost` détecte et anonymise les PII pour que les LLM tiers ne voient jamais les valeurs brutes.

LLM
:   **L**arge **L**anguage **M**odel. Réseau de neurones entraîné sur de grands corpus textuels pour générer ou
    raisonner sur du texte (GPT, Claude, Gemini, Mistral, etc.). Dans ce projet, le LLM est le consommateur en aval
    qui ne doit recevoir que du contenu anonymisé.

NER
:   **N**amed **E**ntity **R**ecognition, reconnaissance d'entités nommées. Tâche de machine learning qui identifie
    les entités nommées dans un texte (personnes, lieux, organisations, dates, etc.). `piighost` utilise
    [GLiNER2](https://github.com/fastino-ai/gliner2) comme moteur NER par défaut via la classe `GlinerDetector`.

Détecteur
:   Composant qui trouve les PII dans un texte. Les détecteurs implémentent le protocole `AnyDetector`.
    Implémentations fournies : `GlinerDetector` (NER), `RegexDetector` (patterns), `ExactMatchDetector` (dictionnaire
    fixe), `CompositeDetector` (chaîne de détecteurs).

Span
:   Intervalle de positions caractères dans un texte : `(start_pos, end_pos)`. Chaque détection porte un `Span` qui
    localise précisément où apparaît la PII. Les spans qui se chevauchent entre plusieurs détecteurs sont arbitrés
    par le résolveur de spans.

Détection
:   Sortie d'un détecteur : un tuple `(texte, label, span, confiance)`. Par exemple, détecter `Patrick`{ .pii } comme
    `PERSON` en position `(0, 7)` avec une confiance de `0.95` produit une `Detection`.

Entité
:   PII logique qui peut apparaître plusieurs fois dans un texte. Produite par le linker d'entités en groupant les
    détections liées (variantes avec fautes de frappe, variantes de casse, mentions partielles). Différent d'une
    `Detection` qui est une occurrence repérée.

Liaison d'entités (entity linking)
:   Étape qui regroupe les détections référant à la même PII réelle. Par exemple, lier `Patrick`{ .pii } en position
    `(0, 7)` et `patrick`{ .pii } en position `(34, 41)` dans une seule `Entity`, afin que les deux occurrences partagent
    le même placeholder.

Placeholder
:   Jeton qui remplace une PII dans le texte anonymisé. Par défaut du type `<<PERSON_1>>`{ .placeholder }, `<<LOCATION_1>>`{ .placeholder }. La
    stratégie de nommage est contrôlée par une `PlaceholderFactory` (compteur, UUID, hash, masqué, caviardé).

Pipeline
:   Orchestration en 5 étapes qui transforme un texte brut en texte anonymisé : Detect, Resolve Spans, Link Entities,
    Resolve Entities, Anonymize. Implémenté par `AnonymizationPipeline` (sans état) et `ThreadAnonymizationPipeline`
    (portée conversation).

Résolveur
:   Composant qui arbitre les conflits. Deux types : `SpanConflictResolver` (détections qui se chevauchent) et
    `EntityConflictResolver` (groupes d'entités liés qui partagent une mention).

Middleware
:   Point d'extension LangChain qui s'exécute avant et après chaque appel au LLM et chaque appel d'outil.
    `PIIAnonymizationMiddleware` s'y branche pour intercepter et transformer les messages, ce qui applique
    l'anonymisation sans modifier le code de l'agent.

Thread
:   Portée de conversation identifiée par un `thread_id`. La mémoire et le cache sont isolés par thread de sorte que
    deux conversations parallèles ne partagent pas l'état des PII.
