---
icon: lucide/shield
---

# PIIGhost

**Anonymisation transparente des données personnelles pour agents LLM.**

`piighost` est une bibliothèque Python qui détecte, anonymise et désanonymise automatiquement les entités sensibles (noms, lieux, etc.) dans les conversations d'agents IA. Elle s'intègre via un middleware LangChain sans modifier votre code d'agent existant.

---

## Fonctionnalités

- **Pipeline 4 étapes** : Detect → Expand → Map → Replace couvre chaque occurrence de chaque entité, pas seulement la première
- **Bidirectionnel** : désanonymisation fiable via des spans inverses, plus une reanonymisation rapide par remplacement de chaîne
- **Cache de session** : protocole `PlaceholderStore` pour la persistance inter-sessions (clé SHA-256)
- **Middleware LangChain** : hooks transparents sur `abefore_model`, `aafter_model`, et `awrap_tool_call` zéro modification de votre code d'agent
- **Injection de dépendances** : chaque étape du pipeline est un protocole swappable detector, occurrence finder, placeholder factory, span validator
- **Modèles immuables** : dataclasses gelées partout (`Entity`, `Placeholder`, `Span`, `AnonymizationResult`)

---

## Installation

=== "uv"

    ```bash
    uv add piighost
    ```

=== "pip"

    ```bash
    pip install piighost
    ```

---

## Exemple rapide

```python
from gliner2 import GLiNER2
from piighost.anonymizer import Anonymizer, GlinerDetector

model = GLiNER2.from_pretrained("fastino/gliner2-multi-v1")
detector = GlinerDetector(model=model, threshold=0.5, flat_ner=True)
anonymizer = Anonymizer(detector=detector)

result = anonymizer.anonymize(
    "Patrick habite à Paris. Patrick aime Paris.",
    labels=["PERSON", "LOCATION"],
)

print(result.anonymized_text)
# <<PERSON_1>> habite à <<LOCATION_1>>. <<PERSON_1>> aime <<LOCATION_1>>.

original = anonymizer.deanonymize(result)
print(original)
# Patrick habite à Paris. Patrick aime Paris.
```

!!! note "Téléchargement du modèle"
    Le modèle GLiNER2 est téléchargé depuis HuggingFace lors de la première utilisation (~500 Mo).

---

## Navigation

| Section | Description |
|---------|-------------|
| [Démarrage rapide](getting-started.md) | Installation et premiers pas |
| [Architecture](architecture.md) | Pipeline et diagrammes de flux |
| [Exemples](examples/basic.md) | Usage basique et intégration LangChain |
| [Détecteurs prêts à l'emploi](examples/detectors.md) | Patterns regex pour PII courants (US & Europe) |
| [Étendre PIIGhost](extending.md) | Créer ses propres modules |
| [Référence API](reference/anonymizer.md) | Documentation complète de l'API |
