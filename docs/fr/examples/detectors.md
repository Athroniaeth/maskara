---
icon: lucide/scan-search
---

# Détecteurs regex prêts à l'emploi

PIIGhost fournit des ensembles de patterns `RegexDetector` dans `examples/detectors/`. Chaque fichier expose un dictionnaire `PATTERNS` et un helper `create_detector()` pour une intégration immédiate.

---

## Patterns disponibles

### Communs (universels)

**Fichier :** `examples/detectors/common.py`

| Label | Exemple |
|-------|---------|
| `EMAIL` | `alice@example.com` |
| `IP_V4` | `192.168.1.42` |
| `IP_V6` | `2001:0db8:85a3::8a2e:0370:7334` |
| `URL` | `https://api.example.com/v1` |
| `CREDIT_CARD` | `4532-1234-5678-9012` |
| `PHONE_INTERNATIONAL` | `+33 6 12 34 56 78` |
| `OPENAI_API_KEY` | `sk-proj-abc123xyz456789ABCDEF` |
| `AWS_ACCESS_KEY` | `AKIAIOSFODNN7EXAMPLE` |
| `GITHUB_TOKEN` | `ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ…` |
| `STRIPE_KEY` | `sk_live_ABCDEFGHIJKLMNOPQR…` |

### Spécifiques US

**Fichier :** `examples/detectors/us.py`

| Label | Exemple | Format |
|-------|---------|--------|
| `US_SSN` | `123-45-6789` | XXX-XX-XXXX |
| `US_PHONE` | `(555) 867-5309` | Avec préfixe +1 optionnel |
| `US_PASSPORT` | `C12345678` | Lettre + 8 chiffres |
| `US_ZIP_CODE` | `90210-1234` | ZIP ou ZIP+4 |
| `US_EIN` | `12-3456789` | Employer Identification Number |
| `US_BANK_ROUTING` | `021000021` | 9 chiffres (ABA routing) |

### Europe

**Fichier :** `examples/detectors/europe.py`

| Label | Exemple | Pays |
|-------|---------|------|
| `EU_IBAN` | `FR7630006000011234567890189` | Pan-EU |
| `EU_VAT` | `FR12345678901` | Pan-EU |
| `FR_SSN` | `185017512345612` | France (INSEE) |
| `FR_PHONE` | `06 12 34 56 78` | France |
| `FR_ZIP` | `75001` | France |
| `DE_PHONE` | `030 1234567` | Allemagne |
| `DE_ZIP` | `10115` | Allemagne |
| `UK_NINO` | `AB123456C` | UK (National Insurance) |
| `UK_NHS` | `943-476-5919` | UK (numéro NHS) |
| `UK_POSTCODE` | `SW1A 1AA` | UK |

---

## Démarrage rapide

### Une seule région

```python
from examples.detectors.common import create_detector
from piighost.anonymizer import Anonymizer

detector = create_detector()
anonymizer = Anonymizer(detector=detector)

result = anonymizer.anonymize("Écrivez-moi à alice@example.com, serveur 192.168.1.42.")
print(result.anonymized_text)
# Écrivez-moi à <<EMAIL_1>>, serveur <<IP_V4_1>>.
```

### Combiner commun + régional

```python
from examples.detectors.europe import create_full_detector
from piighost.anonymizer import Anonymizer

# create_full_detector() fusionne les patterns communs + européens via CompositeDetector
detector = create_full_detector()
anonymizer = Anonymizer(detector=detector)

result = anonymizer.anonymize(
    "IBAN FR7630006000011234567890189, email marie@exemple.fr, tél 06 12 34 56 78."
)
print(result.anonymized_text)
# IBAN <<EU_IBAN_1>>, email <<EMAIL_1>>, tél <<FR_PHONE_1>>.
```

### Sélectionner des patterns à la carte

```python
from piighost.anonymizer import Anonymizer
from piighost.anonymizer.detector import RegexDetector

from examples.detectors.common import PATTERNS as COMMON
from examples.detectors.europe import PATTERNS as EU

# Choisissez uniquement ce dont vous avez besoin
my_patterns = {
    "EMAIL": COMMON["EMAIL"],
    "URL": COMMON["URL"],
    "EU_IBAN": EU["EU_IBAN"],
    "FR_PHONE": EU["FR_PHONE"],
}

detector = RegexDetector(patterns=my_patterns)
anonymizer = Anonymizer(detector=detector)
```

### Combiner avec GLiNER2 (NER + regex)

```python
from gliner2 import GLiNER2
from piighost.anonymizer import Anonymizer, GlinerDetector
from piighost.anonymizer.detector import CompositeDetector
from examples.detectors.common import create_detector as create_regex

model = GLiNER2.from_pretrained("fastino/gliner2-multi-v1")

detector = CompositeDetector(
    detectors=[
        GlinerDetector(model=model, labels=["PERSON", "LOCATION"], threshold=0.5, flat_ner=True),
        create_regex(),  # emails, IPs, URLs, clés API, etc.
    ]
)

anonymizer = Anonymizer(detector=detector)

result = anonymizer.anonymize("Patrick à alice@example.com, IP 10.0.0.1.")
print(result.anonymized_text)
# <<PERSON_1>> à <<EMAIL_1>>, IP <<IP_V4_1>>.
```

---

## Ajouter vos propres patterns

Les ensembles de patterns sont de simples dictionnaires — étendez-les ou créez les vôtres :

```python
from examples.detectors.common import PATTERNS as COMMON

my_patterns = {
    **COMMON,
    "LICENSE_PLATE_FR": r"\b[A-Z]{2}-\d{3}-[A-Z]{2}\b",
    "CUSTOM_ID": r"\bCUST-\d{6}\b",
}
```

Voir aussi [Étendre PIIGhost](../extending.md) pour créer des classes de détecteur entièrement personnalisées.