---
icon: lucide/shield-check
---

# Sécurité

Cette page complète [`SECURITY.md`](https://github.com/Athroniaeth/piighost/blob/master/SECURITY.md) à la racine du
dépôt avec un modèle de menaces : ce contre quoi `piighost` protège, et ce contre quoi il ne protège pas.

## Ce contre quoi `piighost` protège

- **Exfiltration vers les LLM tiers** : le LLM ne voit jamais que des placeholders (`<<PERSON_1>>`, etc.), jamais
  les vraies PII. Même si le prestataire journalise la requête, aucune donnée sensible ne fuit.
- **Fuite via les appels d'outils** : le middleware désanonymise les arguments d'outil juste avant exécution et
  réanonymise les résultats avant qu'ils ne repartent vers le LLM, de sorte que les vraies valeurs ne transitent
  jamais par le contexte visible du LLM.
- **Dérive inter-messages** : le cache lie les variantes (`Patrick` / `patrick`) pour que la même entité garde le
  même placeholder sur toute la conversation, ce qui empêche le LLM de voir la même PII sous différents masques.

## Ce contre quoi `piighost` ne protège pas

- **Compromission de la mémoire locale** : le cache garde le mapping `placeholder -> valeur réelle` en mémoire
  (ou dans le backend que vous avez configuré). Un attaquant ayant accès à la mémoire du processus récupère le
  mapping en clair.
- **Vol disque d'un backend de cache non chiffré** : si vous pointez `aiocache` vers une instance Redis sans
  chiffrement disque, et que quelqu'un repart avec le disque, il repart avec le mapping. Chiffrez le stockage du
  backend.
- **Hallucinations du LLM** : si le LLM invente une PII qui n'était jamais dans l'entrée, `piighost` ne peut pas la
  lier puisqu'elle n'a jamais été mise en cache. Voir [Limites](limitations.md) pour la mitigation.
- **Inférence par canal auxiliaire** : les placeholders préservent la structure du texte. Un adversaire déterminé
  avec une connaissance partielle peut tenter de réidentifier les entités à partir du contexte (rare mais pas
  impossible).
- **Accès amont aux journaux** : `piighost` ne journalise pas les PII brutes, mais votre application peut le
  faire. Auditez vos propres journaux, traces et rapports d'erreurs avant de revendiquer une conformité.

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
