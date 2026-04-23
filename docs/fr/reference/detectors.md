---
icon: lucide/list
tags:
  - Détecteur
  - Regex
---

# Référence Détecteurs prêts à l'emploi

Catalogue des ensembles de patterns `RegexDetector` fournis dans `examples/detectors/`. Chaque fichier expose un dictionnaire `PATTERNS` et un helper `create_detector()`.

Pour les recettes (comment composer, combiner avec un NER, ajouter les siens), voir [Utiliser les détecteurs prêts à l'emploi](../examples/detectors.md).

---

## Communs (universels)

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
| `GITHUB_TOKEN` | `ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ...` |
| `STRIPE_KEY` | `sk_live_ABCDEFGHIJKLMNOPQR...` |

---

## Spécifiques US

**Fichier :** `examples/detectors/us.py`

| Label | Exemple | Format |
|-------|---------|--------|
| `US_SSN` | `123-45-6789` | XXX-XX-XXXX |
| `US_PHONE` | `(555) 867-5309` | Avec préfixe +1 optionnel |
| `US_PASSPORT` | `C12345678` | Lettre + 8 chiffres |
| `US_ZIP_CODE` | `90210-1234` | ZIP ou ZIP+4 |
| `US_EIN` | `12-3456789` | Employer Identification Number |
| `US_BANK_ROUTING` | `021000021` | 9 chiffres (ABA routing) |

---

## Europe

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
