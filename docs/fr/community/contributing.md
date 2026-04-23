---
icon: lucide/git-pull-request
---

# Contribuer

Merci de l'intérêt porté à `piighost`. Cette page résume le workflow de contribution. Pour la version complète, voir [`CONTRIBUTING.md`](https://github.com/Athroniaeth/piighost/blob/master/CONTRIBUTING.md) à la racine du dépôt.

## Prérequis

- Python 3.12+
- [`uv`](https://docs.astral.sh/uv/) comme gestionnaire de paquets
- Un compte GitHub

## Démarrer

1. **Forker** le dépôt sur GitHub.
2. **Cloner** votre fork localement :

    ```bash
    git clone https://github.com/VOTRE-UTILISATEUR/piighost.git
    cd piighost
    git remote add upstream https://github.com/Athroniaeth/piighost.git
    ```

3. **Installer** les dépendances :

    ```bash
    uv sync
    ```

## Workflow

### Créer une branche

Toujours depuis `master` :

```bash
git checkout -b feat/ma-fonctionnalite
```

### Respecter les conventions

- **Protocoles** à toutes les étapes du pipeline pour garder les composants interchangeables.
- **Dataclasses gelées** pour les modèles (`Entity`, `Detection`, `Span`).
- **`ExactMatchDetector`** dans les tests, jamais de vrai modèle NER en CI.
- **Commits conventionnels** via Commitizen (`feat:`, `fix:`, `refactor:`, etc.).

### Vérifications locales

Avant de soumettre une PR :

```bash
make lint       # Format + lint + type-check
uv run pytest   # Suite de tests
```

### Ouvrir la Pull Request

- Titre clair suivant le format Commitizen.
- Description qui explique le *pourquoi* plutôt que le *quoi*.
- Lier l'issue correspondante (`Fixes #42`).
- Screenshots ou exemples de sortie si pertinent.

## Points d'extension

Les endroits les plus courants où contribuer sans toucher au cœur :

- **Nouveau détecteur** : implémenter le protocole `AnyDetector`. Voir [Étendre PIIGhost](../extending.md).
- **Nouveau pack regex** : ajouter un module dans `piighost/detector/patterns/`.
- **Nouveau validateur** : fonction `Callable[[str], bool]` dans `piighost/validators.py`.
- **Nouvelle factory de placeholders** : implémenter `AnyPlaceholderFactory`.
