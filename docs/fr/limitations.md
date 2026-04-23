---
icon: lucide/triangle-alert
---

# Limites

`piighost` n'est pas une solution miracle. Cette page liste les limites connues, leur raison d'être et comment les
atténuer.

## La couverture linguistique dépend du modèle

L'ensemble des langues que `piighost` peut anonymiser est déterminé par le modèle NER branché sur le détecteur NER
(`GlinerDetector` dans la configuration par défaut, qui encapsule GLiNER2). Par exemple, `fastino/gliner2-multi-v1`
couvre plusieurs langues mais pas toutes avec la même précision. Avant de déployer sur une nouvelle locale, lisez
la fiche du modèle et exécutez un petit jeu de validation.

**Mitigation** : chargez un modèle spécifique à la locale pour une meilleure précision, ou combinez plusieurs
détecteurs via le détecteur composite (`CompositeDetector`).

## Les faux négatifs NER sont inhérents

Aucun modèle NER n'est parfait. Des noms rares, des orthographes inhabituelles ou des entités hors distribution
peuvent être manquées. Pour les catégories critiques (emails, numéros de téléphone, identifiants nationaux),
s'appuyer uniquement sur la NER est risqué.

**Mitigation** : chaînez le détecteur NER (`GlinerDetector`) avec un détecteur à motif (`RegexDetector`) via le
détecteur composite (`CompositeDetector`) pour une couverture déterministe des formats de PII structurés. Voir
[Étendre PIIGhost](extending.md) pour les recettes.

## Les PII générées par le LLM ne sont pas liées

La liaison d'entités fonctionne sur les détections issues de l'entrée. Si le LLM hallucine un nom qui n'est jamais
apparu dans les messages de l'utilisateur (par exemple en inventant un nom de client plausible), cette PII
hallucinée n'est pas dans le cache et n'est donc pas anonymisée lorsque la réponse repasse par le middleware.

**Mitigation** : exécutez une étape de validation post-réponse au niveau applicatif. Redétectez les PII sur la
sortie du LLM et décidez s'il faut les supprimer, les signaler ou les réanonymiser avant affichage à l'utilisateur.

## Le cache est en mémoire par défaut

La pipeline d'anonymisation (`AnonymizationPipeline`) utilise `aiocache` avec un backend en mémoire par défaut.
C'est correct pour un déploiement mono-processus, mais cela casse dès que vous passez à l'échelle horizontalement
(deux workers, deux caches, deux espaces de placeholders indépendants).

**Mitigation** : configurez un backend de cache externe supporté par `aiocache` (Redis, Memcached). Voir
[Déploiement](deployment.md) pour les exemples de configuration.

## La latence ajoutée n'est pas encore mesurée

Il n'existe pas de benchmark officiel de la latence ajoutée par le pipeline sur des charges typiques. L'overhead
dépend du détecteur (inférence du NER choisi), de la longueur du texte, et de la présence de hits dans le cache.

**Mitigation** : mesurez sur votre propre charge avant de dimensionner le trafic de production. Gardez les
détecteurs sur GPU quand c'est possible pour les chemins à forte densité NER.

## Couverture minimale des menaces

`piighost` traite l'exfiltration *vers le LLM et son hébergeur*. Elle ne remplace pas le chiffrement au repos, le
contrôle d'accès, ni les bonnes pratiques de journalisation du reste de votre système. Voir [Sécurité](security.md)
pour le modèle de menaces complet.
