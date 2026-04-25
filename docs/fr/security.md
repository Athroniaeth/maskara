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

## `repr()` masqué sur les dataclasses porteuses de PII

La dataclass `Detection` porte la forme brute de la PII dans son champ
`text`. Pour éviter les fuites accidentelles via `print(detection)`,
`logger.info("got %s", detection)` ou une traceback non rattrapée,
`__repr__` masque ce champ :

```python
>>> from piighost.models import Detection, Span
>>> d = Detection(text="Patrick", label="PERSON", position=Span(0, 7), confidence=0.9)
>>> repr(d)
"Detection(text=<redacted:7>, label='PERSON', position=Span(start_pos=0, end_pos=7), confidence=0.9)"
```

`Entity.__repr__` hérite gratuitement du masquage puisqu'il rend ses
`Detection` via `repr()`. `Span` n'est pas masqué : les positions sont
des métadonnées, pas du contenu.

Il s'agit d'une protection de type « garde-fou », pas d'un substitut à
la discipline. La valeur brute reste accessible via `detection.text` ;
tout code qui imprime ou journalise explicitement cet attribut
contourne le masquage. `SecretStr` de Pydantic n'est pas utilisé pour
garder minimale la surface de dépendances principales de `piighost`.

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
