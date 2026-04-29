---
icon: lucide/shield-check
---

# Sécurité

Cette page complète [`SECURITY.md`](https://github.com/Athroniaeth/piighost/blob/master/SECURITY.md) à la racine du
dépôt avec un modèle de menaces : ce contre quoi `piighost` protège, et ce contre quoi il ne protège pas.

## Ce contre quoi `piighost` protège

!!! success "Dans le périmètre de protection"
    - **Exfiltration vers les LLM tiers** : le LLM ne voit jamais que des placeholders (`<<PERSON:1>>`{ .placeholder }, etc.),
      jamais les vraies PII. Même si le prestataire journalise la requête, aucune donnée sensible ne fuit.
    - **Fuite via les appels d'outils** : le middleware désanonymise les arguments d'outil juste avant exécution
      et réanonymise les résultats avant qu'ils ne repartent vers le LLM, de sorte que les vraies valeurs ne
      transitent jamais par le contexte visible du LLM.
    - **Dérive inter-messages** : le cache lie les variantes (`Patrick`{ .pii } / `patrick`{ .pii }) pour que la même entité
      garde le même placeholder sur toute la conversation, ce qui empêche le LLM de voir la même PII sous
      différents masques.

## Ce contre quoi `piighost` ne protège pas

!!! danger "Hors du périmètre de protection"
    - **Compromission de la mémoire locale** : le cache garde le mapping `placeholder -> valeur réelle` en
      mémoire (ou dans le backend que vous avez configuré). Un attaquant ayant accès à la mémoire du processus
      récupère le mapping en clair.
    - **Vol disque d'un backend de cache non chiffré** : si vous pointez `aiocache` vers une instance Redis sans
      chiffrement disque, et que quelqu'un repart avec le disque, il repart avec le mapping. Chiffrez le stockage
      du backend.
    - **Hallucinations du LLM** : si le LLM invente une PII qui n'était jamais dans l'entrée, `piighost` ne peut
      pas la lier puisqu'elle n'a jamais été mise en cache. Voir [Limites](limitations.md) pour la mitigation.
    - **Inférence par canal auxiliaire** : les placeholders préservent la structure du texte. Un adversaire
      déterminé avec une connaissance partielle peut tenter de réidentifier les entités à partir du contexte
      (rare mais pas impossible).
    - **Accès amont aux journaux** : `piighost` ne journalise pas les PII brutes, mais votre application peut le
      faire. Auditez vos propres journaux, traces et rapports d'erreurs avant de revendiquer une conformité.

## Discipline de journalisation pour les dataclasses porteuses de PII

La dataclass `Detection` porte la forme brute de la PII dans son champ
`text`. Le `__repr__` généré par dataclass affiche cette valeur en
clair, ce qui rend l'API prévisible pour l'inspection, le debug et les
tests :

```python
>>> from piighost.models import Detection, Span
>>> d = Detection(text="Patrick", label="PERSON", position=Span(0, 7), confidence=0.9)
>>> repr(d)
"Detection(text='Patrick', label='PERSON', position=Span(start_pos=0, end_pos=7), confidence=0.9)"
```

La bibliothèque ne masque délibérément pas ce champ. Si vous
transférez des instances `Detection` ou `Entity` vers des logs, des
traces ou un reporter d'erreurs, faites le scrub vous-même. Deux
recettes simples :

- Filtrer `to_dict()` avant sérialisation (retirer la clé `text`).
- Encapsuler votre logger structuré dans un redactor qui reconnaît les
  `Detection` et remplace `text` par un marqueur de longueur.

`piighost` lui-même n'écrit jamais de PII dans aucun logger ; la
discipline ci-dessus est nécessaire dans votre propre code.

## Redaction des payloads d'observation

Quand le pipeline est configuré avec un `AbstractObservationService`
(par exemple `LangfuseObservationService`), chaque étape produit une
observation enfant avec ses propres `input` et `output`. Le pipeline
applique une placeholder factory dédiée à l'observation pour
remplacer chaque PII détectée avant de pousser le payload vers le
backend. Le défaut est `RedactPlaceholderFactory()`, qui collapse
toute entité sur `<<REDACT>>` :

```text
texte utilisateur     : "Patrick habite à Paris."
payload d'observation : "<<REDACT>> habite à <<REDACT>>."
```

Concrètement :

- l'`input` du span racine, du stage `detect` et du stage
  `placeholder` est rempli avec le texte rédigé par la factory une
  fois la détection terminée. Tant que la détection n'a pas tourné,
  le span racine n'a pas d'`input` du tout, donc rien ne fuit avant
  d'avoir un mapping fiable,
- les `Detection` et `Entity` sérialisées dans `detect.output` et
  `link.input/output` portent le token de la factory à la place de
  leur champ `text`. Le label, la position et la confidence restent
  visibles pour le débogage,
- les payloads déjà anonymisés (`placeholder.output`,
  `guard.input/output`, `output` du span racine) passent inchangés
  puisqu'ils ne contiennent que des placeholders.

Cette politique protège l'entrée utilisateur même si le pipeline
échoue avant d'avoir produit le texte anonymisé final. Un crash au
stage `link` ou `placeholder` ne fait pas fuiter la PII brute vers
Langfuse, parce que tout ce qui a été poussé jusque-là porte déjà
des placeholders d'observation.

Pour surfacer plus de structure (par exemple une numérotation
distincte par PII en environnement de dev), passer une autre factory
au constructeur :

```python
from piighost.placeholder import RedactCounterPlaceholderFactory

pipeline = ThreadAnonymizationPipeline(
    detector=detector,
    anonymizer=anonymizer,
    observation=LangfuseObservationService(client),
    observation_ph_factory=RedactCounterPlaceholderFactory(),  # <<REDACT:1>>, <<REDACT:2>>, ...
)
```

N'importe quelle implémentation de `AnyPlaceholderFactory` est
acceptée. La factory d'observation est indépendante de celle qui
sert à l'anonymisation réelle, donc on peut afficher du
`<<PERSON:1>>` côté Langfuse tout en gardant un faux nom Faker côté
LLM.

## Décisions de conception qui soutiennent le modèle de menaces

- **L'anonymisation est locale** : les PII sont remplacées avant que la requête HTTP n'atteigne le fournisseur du
  LLM.
- **Cache clé SHA-256** : les placeholders sont dérivés de manière déterministe, pas stockés en clair sous le label
  du placeholder. Même un dump du cache ne révèle pas quel placeholder mappe à quelle PII sans le sel.
- **Aucune journalisation des PII brutes par la bibliothèque** : `piighost` lui-même n'écrit jamais de PII dans un
  logger. Votre propre code doit suivre la même discipline.
- **Dataclasses gelées** : `Entity`, `Detection`, `Span` sont immuables, ce qui empêche la mutation accidentelle
  après que l'anonymisation a été appliquée.

## Signaler une vulnérabilité

Voir [`SECURITY.md`](https://github.com/Athroniaeth/piighost/blob/master/SECURITY.md) pour le canal privé de
signalement de vulnérabilités et la matrice des versions supportées.
