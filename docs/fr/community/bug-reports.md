---
icon: lucide/bug
---

# Signaler un bug

Un bon rapport de bug fait gagner du temps à tout le monde. Avant d'ouvrir une issue, quelques vérifications rapides.

## Avant d'ouvrir une issue

1. **Vérifier la version** : reproduisez sur la dernière version publiée (`pip install -U piighost` ou `uv lock --upgrade-package piighost`).
2. **Chercher dans les issues existantes** : [issues ouvertes et fermées](https://github.com/Athroniaeth/piighost/issues?q=is%3Aissue).
3. **Isoler le problème** : le bug survient-il avec `ExactMatchDetector` (qui ne charge aucun modèle NER) ou seulement avec le détecteur NER ? La différence aide à localiser la cause.

## Ce qu'un bon rapport contient

!!! example "Gabarit minimal"
    - **Version de `piighost`** (`uv run python -c "import piighost; print(piighost.__version__)"`)
    - **Version de Python**
    - **Détecteur utilisé** (GLiNER2, spaCy, regex, composite…)
    - **Entrée minimale** qui reproduit le bug (quelques lignes, pas tout un jeu de données)
    - **Sortie observée**
    - **Sortie attendue**
    - **Traceback complet** si exception, dans un bloc de code
    - **Environnement** : OS, GPU/CPU, autres détecteurs chargés

## Ce qu'il faut éviter

- Rapports à haut niveau du type "l'anonymisation ne marche pas" sans exemple reproductible.
- Captures d'écran de code à la place d'un bloc texte (impossible à copier-coller pour reproduire).
- Partager de vraies PII dans l'issue. Utilisez des valeurs factices (`Alice Dupont`, `Paris`, `alice@example.com`).

## Vulnérabilités de sécurité

**Ne pas** ouvrir d'issue publique pour une vulnérabilité. Utilisez le [canal privé de signalement GitHub](https://github.com/Athroniaeth/piighost/security/advisories/new). Voir [Sécurité](../security.md) pour le modèle de menaces et ce que `piighost` protège ou ne protège pas.

## Où ouvrir l'issue

[github.com/Athroniaeth/piighost/issues/new](https://github.com/Athroniaeth/piighost/issues/new)
