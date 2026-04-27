Ça fait un moment que je construis des agents avec LangGraph, et je retombe toujours sur le même problème : chaque message envoyé au LLM peut contenir des données sensibles, et selon le fournisseur que vous utilisez, ce qu'il advient de ces données change complètement.

En simplifiant, il y a trois familles de fournisseurs :

- **Cloud non-européen** (OpenAI, Anthropic, Google) : les meilleurs modèles, mais les données quittent l'UE, ce qui est problématique sur plein d'aspects. J'en ai fait un résumé [ici](https://athroniaeth.github.io/piighost/fr/why-anonymize/#fonctionnement-dun-llm-cloud).
- **Cloud souverain européen** (Mistral, Aleph Alpha) : traitement en UE, mais catalogue plus restreint.
- **Self-hosted** (Ollama, vLLM, modèles open-weight) : vous ne fournissez jamais vos données à un tiers, vous contrôlez tout, mais vous devez gérer l'infrastructure vous-même.

Je travaille actuellement sur des documents notariaux, ce qui me limite en pratique à Mistral. Je ne peux donc pas profiter des meilleurs LLM pour effectuer mes tâches. La seule façon propre de découpler le LLM de la sensibilité du contenu, c'est d'anonymiser en amont.

## Pourquoi c'est plus dur qu'il n'y paraît

Sur le papier, c'est simple : on prend un détecteur (regex pour les emails, modèle NER pour les noms), on remplace ce qui matche par des placeholders, et on envoie au LLM.

En pratique, quatre problèmes apparaissent presque immédiatement.

**Cohérence des placeholders.** Le but de l'anonymisation est de remplacer "Patrick" par un placeholder du type `<<PERSON:1>>`, qui dit deux choses au LLM : on a caché une personne ici, et toutes les occurrences de `<<PERSON:1>>` parlent de la même personne. Si "Patrick" devient `<<PERSON:1>>` au début du texte et `<<PERSON:3>>` à la fin, le LLM ne peut plus raisonner sur le fait qu'il s'agit du même individu.

**Variantes ratées par le détecteur.** Le NER détecte "Patrick Dupont" en début de texte mais rate "Patrick" tout seul deux phrases plus loin. Ou il détecte "Patrick" mais pas "patrick" en bas de casse. Ou pas "Patriick" avec une faute d'orthographe.

**Chevauchement entre détecteurs.** Vous chaînez deux NER pour augmenter le rappel. Sur "Patrick", les deux peuvent revendiquer le même span avec des labels différents (l'un dit `PERSON`, l'autre dit `ORG` parce qu'il a confondu avec un nom d'entreprise). Sans arbitrage, le remplacement final tape sur la même position deux fois et casse le texte.

**Persistance entre messages.** Une fois que le LLM a vu `<<PERSON:1>>` dans le message 1, il faut que le message 2 utilise le même placeholder. Sans mémoire partagée, "Patrick" devient `<<PERSON:1>>` puis `<<PERSON:7>>` selon le moment, et le LLM perd le fil.

Et c'est avant même de parler de l'agent, où les outils doivent recevoir les vraies valeurs (pour envoyer un email, par exemple) tandis que le LLM ne doit voir que les placeholders. Côté front, il faut aussi désanonymiser les placeholders avant de montrer la réponse à l'utilisateur, sans que le LLM ait connaissance du mapping.

C'est pour répondre à tout ça que j'ai construit **PIIGhost**, un projet open-source qui ajoute une couche de détection, d'anonymisation et de désanonymisation par-dessus vos détecteurs (NER, regex, LLM, ce que vous voulez). Il propose en plus un mode conversationnel et un middleware LangChain qui s'intègre dans LangGraph sans modifier votre code existant.

Le reste de l'article suit l'ordre du pipeline : détection, arbitrage des spans, liaison d'entités, fusion, anonymisation, puis les couches conversationnelle et agent.

---

## Étape 1 : Détection

Tout commence par la détection. Un détecteur prend du texte et retourne une liste d'objets `Detection` (texte trouvé, label, position, confiance). PIIGhost en fournit plusieurs en standard :

- `RegexDetector` pour les formats structurés (emails, téléphones, IBAN).
- `ExactMatchDetector` pour des mots fixes connus à l'avance, utile pour les tests ou pour des dictionnaires métier.
- `Gliner2Detector` pour le NER, branché sur GLiNER2 par défaut.
- `CompositeDetector` pour combiner plusieurs détecteurs en un seul.

L'interface est un protocole `AnyDetector`, donc vous pouvez brancher le vôtre (un appel LLM, un autre modèle NER, ce que vous voulez).

Voici un exemple sans modèle ML, juste pour montrer la mécanique :

```python
from piighost import ExactMatchDetector

detector = ExactMatchDetector([
    ("Patrick", "PERSON"),
    ("Paris", "LOCATION"),
])

detections = await detector.detect("Patrick habite à Paris.")
# Detection(text='Patrick', label='PERSON',   position=Span(0, 7),   confidence=1.0)
# Detection(text='Paris',   label='LOCATION', position=Span(17, 22), confidence=1.0)
```

À ce stade, on a une liste brute de détections. Pas encore d'anonymisation, pas de gestion de doublons, rien. Juste : "voici ce qui ressemble à des PII et où elles sont".

---

## Étape 2 : Arbitrage des spans

Premier vrai problème : quand vous chaînez plusieurs détecteurs sur le même texte, ils peuvent revendiquer le même morceau avec des labels différents. C'est typiquement ce qui arrive quand on combine deux NER pour augmenter le rappel : ils se marchent dessus et l'un des deux se trompe.

Prenons un exemple concret. Sur la phrase suivante :

> "Patrick travaille chez Orange depuis 2015."

Vous faites tourner deux NER :

- NER A (un modèle généraliste) détecte "Patrick" → `PERSON`, span `[0:7]`, confidence `0.95`
- NER B (un modèle métier moins fiable sur les prénoms) détecte "Patrick" → `ORG`, span `[0:7]`, confidence `0.60` (il a confondu avec un nom d'entreprise)

Les deux pointent exactement sur le même span `[0:7]`, mais avec des labels qui s'excluent mutuellement. Si on remplace les deux, on tape deux fois sur la même position et on obtient un truc cassé du genre `<<ORG:1>><<PERSON:1>> travaille chez...`. Il faut choisir.

C'est le rôle du **résolveur de spans**. PIIGhost en fournit deux par défaut :

- `ConfidenceSpanConflictResolver` : garde la détection avec la plus haute confiance en cas de chevauchement. C'est le défaut raisonnable.
- `DisabledSpanConflictResolver` : ne fait rien, à utiliser si vos détections sont déjà propres ou si vous voulez gérer le cas vous-même.

Vous pouvez aussi écrire le vôtre (préférer le span le plus long, préférer un label spécifique, etc.) en implémentant le protocole `SpanConflictResolver`.

```python
from piighost import ConfidenceSpanConflictResolver

resolver = ConfidenceSpanConflictResolver()
clean = resolver.resolve(detections)

# Détections en entrée :
#   - PERSON "Patrick" [0:7] confidence=0.95   (NER A)
#   - ORG    "Patrick" [0:7] confidence=0.60   (NER B)
#
# Après résolution, il ne reste que :
#   - PERSON "Patrick" [0:7] confidence=0.95
```

À la fin de cette étape, plus de chevauchements. Chaque morceau de texte n'est revendiqué que par une seule détection.

> Le chevauchement n'est pas forcément exact. Le résolveur gère aussi les cas où un span est inclus dans un autre, ou où deux spans se recouvrent partiellement. Le principe reste le même : garder le plus confiant.

---

## Étape 3 : Liaison d'entités

Deuxième problème : le NER rate des occurrences. Il trouve "Patrick Dupont" dans la phrase 1, mais rate "Patrick" tout seul dans la phrase 3. Si on s'arrête à la détection brute, "Patrick" reste en clair dans le texte anonymisé. C'est exactement ce qu'on veut éviter.

Le **linker** corrige ça. `ExactEntityLinker` fait deux choses :

1. Pour chaque détection, il cherche toutes les autres occurrences du même texte dans le document, avec une regex word-boundary (pour éviter de matcher "Patric" dans "Patricia").
2. Il regroupe toutes les détections qui pointent vers le même texte normalisé en un seul objet `Entity`.

Concrètement :

```text
Texte : "Patrick Dupont habite à Paris. Patrick adore Paris."

Détections brutes du NER :
  - PERSON   "Patrick Dupont"  (phrase 1)
  - LOCATION "Paris"            (phrase 1)
  # "Patrick" et "Paris" de la phrase 2 ont été ratés par le NER

Après ExactEntityLinker :
  - Entity(label=PERSON,   detections=["Patrick Dupont", "Patrick"])
  - Entity(label=LOCATION, detections=["Paris", "Paris"])
```

Toutes les occurrences sont retrouvées, regroupées par entité. Le NER rate des choses, le linker rattrape derrière.

> À noter : le linker fait du matching exact sur la chaîne. Il n'attrape pas "patrick" en bas de casse ou "Patriick" avec une faute. Pour ça, il faut un linker fuzzy, qu'on peut écrire en implémentant le protocole `EntityLinker`.

---

## Étape 4 : Fusion d'entités

Troisième problème, plus subtil. Imaginez deux détecteurs qui voient la même personne mais avec des spans différents :

- Le NER détecte "Patrick Dupont" → entité A, label `PERSON`
- Un dictionnaire métier détecte "Patrick" tout seul (parce qu'il est dans la liste des associés du cabinet) → entité B, label `PERSON`

Après le linker, vous vous retrouvez avec deux entités distinctes alors qu'il s'agit clairement de la même personne. Si vous anonymisez tel quel, "Patrick Dupont" devient `<<PERSON:1>>` et "Patrick" tout seul devient `<<PERSON:2>>`. Le LLM pense que ce sont deux personnes différentes.

Le **resolver d'entités** fusionne ces doublons. Deux options :

- `MergeEntityConflictResolver` : utilise un union-find pour fusionner les entités qui partagent au moins une détection en commun (matching strict). C'est le défaut.
- `FuzzyEntityConflictResolver` : utilise la distance Jaro-Winkler pour fusionner les entités dont le texte canonique est proche (ex. "Patrick" et "Patriick" avec une typo). Plus tolérant, mais risque de faux positifs plus élevé.

Exemple concret :

```text
Avant fusion :
  - Entity(label=PERSON, detections=["Patrick Dupont"])
  - Entity(label=PERSON, detections=["Patrick"])
  # Les deux entités partagent une détection sur la chaîne "Patrick"

Après MergeEntityConflictResolver :
  - Entity(label=PERSON, detections=["Patrick Dupont", "Patrick"])
```

À ce stade, vous avez une liste propre d'entités, chacune regroupant toutes ses occurrences. Plus de doublons, plus de chevauchements.

---

## Étape 5 : Anonymisation

Maintenant on peut remplacer. L'`Anonymizer` génère un placeholder unique par entité via une `PlaceholderFactory`, puis remplace les spans dans le texte de droite à gauche (pour ne pas décaler les positions des spans suivants).

```python
from piighost import Anonymizer, LabelCounterPlaceholderFactory

anonymizer = Anonymizer(LabelCounterPlaceholderFactory())
result = anonymizer.anonymize(text, entities)

# Patrick Dupont habite à Paris. Patrick adore Paris.
# devient
# <<PERSON:1>> habite à <<LOCATION:1>>. <<PERSON:1>> adore <<LOCATION:1>>.
```

Plusieurs factories sont fournies, à choisir selon votre cas :

- `LabelCounterPlaceholderFactory` : `<<PERSON:1>>`, `<<LOCATION:1>>`. Lisible dans les logs et les traces.
- `LabelHashPlaceholderFactory` : `<<PERSON:a3f9>>`. Évite de fuiter l'ordre d'apparition des entités d'une conversation à l'autre.
- `FakerCounterPlaceholderFactory` : "John Smith", "Springfield". Préserve le flux linguistique pour le LLM (utile si le modèle galère avec les placeholders bruts).
- `MaskPlaceholderFactory` : `[REDACTED]`. Anonymisation pure, irréversible.

Le format `<<LABEL:N>>` par défaut a quatre propriétés utiles :

- il est en théorie unique comme token,
- le LLM voit immédiatement de quel type de PII il s'agit,
- il n'est pas ambigu dans du texte normal,
- il ne peut pas être confondu avec un autre placeholder (contrairement à `<<PERSON>>` tout court, qui ne distingue pas les personnes entre elles).

---

## Le pipeline assemblé

Toutes les étapes ci-dessus s'enchaînent dans un pipeline :

```python
from piighost.pipeline import AnonymizationPipeline
from piighost import (
    ConfidenceSpanConflictResolver,
    ExactEntityLinker,
    MergeEntityConflictResolver,
    Anonymizer,
    LabelCounterPlaceholderFactory,
)

pipeline = AnonymizationPipeline(
    detector=detector,
    span_resolver=ConfidenceSpanConflictResolver(),
    entity_linker=ExactEntityLinker(),
    entity_resolver=MergeEntityConflictResolver(),
    anonymizer=Anonymizer(LabelCounterPlaceholderFactory()),
)

anonymized, entities = await pipeline.anonymize(
    "Patrick Dupont habite à Paris. Patrick adore Paris."
)
# <<PERSON:1>> habite à <<LOCATION:1>>. <<PERSON:1>> adore <<LOCATION:1>>.

original, _ = await pipeline.deanonymize(anonymized)
# Patrick Dupont habite à Paris. Patrick adore Paris.
```

Le pipeline garde un cache du mapping (clé SHA-256 sur le texte d'entrée), donc la désanonymisation est gratuite après le premier appel.

---

## Le problème de la conversation

Tout ça marche pour un message isolé. Dans une vraie conversation, ça casse à cause de trois problèmes.

**Compteurs non partagés.** Chaque appel à `anonymize` repart de zéro. Le mapping `Patrick → <<PERSON:1>>` du message 1 n'est pas garanti d'être réutilisé au message 2.

**Détections manquées entre messages.** Le NER détecte "Patrick" dans le message 1 mais le rate dans le message 5. Sans mémoire des entités déjà vues, on ne peut pas combler le trou.

**Conversations concurrentes.** Si plusieurs utilisateurs partagent la même instance de pipeline, leurs entités se mélangent. Les `<<PERSON:1>>` des uns et des autres deviennent indiscernables.

Démonstration du bug :

```python
# Message 1
m1, _ = await pipeline.anonymize("Patrick habite à Paris.")
# <<PERSON:1>> habite à <<LOCATION:1>>.

# Message 2 : état non partagé
m2, _ = await pipeline.anonymize("Bob est content.")
# <<PERSON:1>> est content.   ← le compteur est reparti à 1
# Bob hérite donc du même placeholder que Patrick → collision :
# le LLM pense que c'est la même personne.
```

`ThreadAnonymizationPipeline` étend le pipeline standard avec une `ConversationMemory` scopée par `thread_id`. La mémoire accumule les entités au fil des messages, dédupliquées par `(text.lower(), label)`. Chaque appel passe un `thread_id`, et le cache est préfixé par cet identifiant pour isoler les conversations.

```python
from piighost.pipeline.thread import ThreadAnonymizationPipeline

pipeline = ThreadAnonymizationPipeline(detector=..., span_resolver=..., ...)

# Conversation A
m1, _ = await pipeline.anonymize("Patrick habite à Paris.", thread_id="user-A")
# <<PERSON:1>> habite à <<LOCATION:1>>.

m2, _ = await pipeline.anonymize("Patrick est content.", thread_id="user-A")
# <<PERSON:1>> est content.   ← garanti, partagé via la mémoire du thread

# Conversation B en parallèle, isolée
m3, _ = await pipeline.anonymize("Bob aime Lyon.", thread_id="user-B")
# <<PERSON:1>> aime <<LOCATION:1>>.   ← compteur indépendant de la conversation A
```

`ThreadAnonymizationPipeline` ajoute aussi deux opérations utiles pour le cas agent :

- `anonymize_with_ent(text, thread_id=...)` : remplacement de chaîne pur, sans détection. Utilise les entités déjà connues du thread pour anonymiser un nouveau texte. Plus rapide, mais ne détecte pas de nouvelles PII.
- `deanonymize_with_ent(text, thread_id=...)` : remplacement inverse. Utile quand le LLM produit un texte avec des placeholders qu'on veut restaurer.

Ces deux opérations gèrent correctement les cas où un placeholder est préfixe d'un autre (`<<PERSON:1>>` vs `<<PERSON:10>>`) en remplaçant les plus longs en premier.

---

## Le problème de l'agent

Dans un agent LangGraph, le LLM ne traite pas juste des messages. Il appelle des outils, lit leurs résultats, et raisonne en boucle. Anonymiser proprement dans ce contexte demande trois interventions à des moments précis.

**Avant l'appel LLM.** Tous les messages doivent être anonymisés. C'est le `pipeline.anonymize()` standard, appliqué sur chaque message du contexte.

**Avant et après l'exécution d'un outil.** Le LLM appelle `send_email(to=<<PERSON:1>>)`. Le tool a besoin de la vraie adresse, pas du placeholder. On désanonymise les arguments via `deanonymize_with_ent`, on exécute, puis on réanonymise le résultat avant de le redonner au LLM.

**Avant l'affichage à l'utilisateur.** Le LLM produit "C'est fait, j'ai envoyé l'email à `<<PERSON:1>>`". L'utilisateur veut voir "Patrick", pas le placeholder.

`PIIAnonymizationMiddleware` pose ces trois hooks dans LangGraph :

```python
from langchain.agents import create_agent
from piighost.middleware import PIIAnonymizationMiddleware

middleware = PIIAnonymizationMiddleware(pipeline=pipeline)

agent = create_agent(
    model="mistral:mistral-large-latest",
    tools=[send_email, get_weather],
    middleware=[middleware],
)
```

Sous le capot, le middleware lit le `thread_id` depuis la config LangGraph (`get_config()["configurable"]["thread_id"]`) et le passe à toutes les opérations du pipeline. Le LLM ne voit jamais les vraies valeurs, les outils les reçoivent normalement, l'utilisateur récupère sa réponse avec ses noms intacts. Aucun code agent à modifier.

---

## piighost-chat : la démo human-in-the-loop

Pour rendre tout ça concret, j'ai construit un chatbot par-dessus la librairie. L'utilisateur voit ce qui va être anonymisé avant que le message parte au LLM. Il peut désélectionner un span flaggué par erreur, ou sélectionner du texte que le détecteur a raté. Une fois validé, le message part dans la pipeline.

![Application piighost-chat](https://dev-to-uploads.s3.amazonaws.com/uploads/articles/pac3ix2cnjrdi9y8si31.png)


Ce genre d'UX human-in-the-loop est ce qui rend l'anonymisation automatique vraiment utilisable dans les workflows réels, où la précision automatique plafonne souvent autour de 90-95 % et où ces quelques pourcents manqués peuvent être problématiques. La passe automatique fait le gros du boulot, l'humain rattrape les bords.

Par exemple ici vous rentrez votre message, il passe par l'API piighost et le front affiche ce qui a été détecté et ce qui va être anonymisé.

![Détection automatique des PII avant envoi au LLM](https://dev-to-uploads.s3.amazonaws.com/uploads/articles/0zji4sbp1pwcsg2l43rs.png)

Vous pouvez supprimer des entités anonymisées s'il y a eu un faux positif.

![Suppression manuelle d'un faux positif](https://dev-to-uploads.s3.amazonaws.com/uploads/articles/7i5u9da5v7t63qlsnop9.png)

Vous pouvez aussi sélectionner du texte pour rajouter des entités à anonymiser.

![Sélection manuelle d'une PII oubliée par le détecteur](https://dev-to-uploads.s3.amazonaws.com/uploads/articles/heaxmgmlhpxuu3s8ns5f.png)

![L'entité ajoutée apparaît dans la liste des PII anonymisées](https://dev-to-uploads.s3.amazonaws.com/uploads/articles/e5n1ni84nrudib57wtql.png)

Si vous demandez des informations sur une PII anonymisée, par exemple par quelle lettre commence le mot, le LLM ne pourra pas vous répondre.

![Le LLM, ne voyant que le placeholder, est incapable de répondre sur le contenu réel](https://dev-to-uploads.s3.amazonaws.com/uploads/articles/a4eccg4abdie2bu7685a.png)

---

La librairie est à ses débuts. J'ai essayé d'anticiper un maximum de cas en partant de mes propres besoins sur des documents notariaux, mais je sais que c'est un angle particulier et que beaucoup de choses peuvent être discutées : des composants pas assez génériques, des abstractions qui ne servent à rien, des cas d'usage que je n'ai pas vus.
Si vous l'essayez, vos retours m'intéressent vraiment :

ce qui vous a manqué ou paru contre-intuitif,
ce qui vous semble trop complexe ou inutile et mériterait d'être supprimé,
les cas d'usage où elle ne tient pas la route.

Tout est bon à prendre, que ce soit via une issue GitHub, une PR, ou même un message direct. Je préfère trancher tôt sur ce qui n'a pas sa place plutôt que d'accumuler de la dette.

- [piighost](https://github.com/Athroniaeth/piighost)
- [piighost-chat](https://github.com/Athroniaeth/piighost-chat)
- [Documentation](https://athroniaeth.github.io/piighost/fr/)

Merci d'avoir lu.