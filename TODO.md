# TODO — PIIGhost

Fonctionnalités manquantes identifiées par analyse comparative avec [PIICloak](https://github.com/dimanjet/piicloak), [pii-guard](https://pypi.org/project/pii-guard/), et [pII-guard](https://github.com/rpgeeganage/pII-guard).

## Priorité haute

- [ ] **Détecteurs PII prêts à l'emploi** — Fournir des `RegexDetector` préconfigurés pour les types PII courants :
  - [ ] Email
  - [ ] Numéro de téléphone (formats internationaux)
  - [ ] Carte de crédit
  - [ ] SSN (US)
  - [ ] IBAN
  - [ ] Adresse IP (v4/v6)
  - [ ] URL
  - [ ] Clé API (OpenAI, AWS, GitHub, Stripe)
  - [ ] Passeport
  - [ ] Permis de conduire

- [ ] **Stratégies d'anonymisation supplémentaires** — Nouveaux `PlaceholderFactory` :
  - [ ] Masquage partiel (`MaskPlaceholderFactory`) — ex: `****4567`, `j***@email.com`
  - [ ] Suppression pure (`RedactPlaceholderFactory`) — ex: `[REDACTED]`
  - [ ] Génération de fausses données (`FakerPlaceholderFactory`) — utiliser Faker (déjà en dépendance) pour générer des noms, adresses, emails réalistes

## Priorité moyenne

- [ ] **Validateurs d'entités** — Protocole `EntityValidator` post-détection :
  - [ ] Algorithme de Luhn (cartes de crédit)
  - [ ] Checksum IBAN
  - [ ] Format email (RFC 5322)
  - [ ] Plages IP valides

- [ ] **API REST dédiée** — Endpoints indépendants du LLM :
  - [ ] `POST /detect` — détection seule, retourne les entités trouvées
  - [ ] `POST /anonymize` — anonymise un texte
  - [ ] `POST /deanonymize` — deanonymise un texte à partir d'un session ID
  - [ ] `GET /health` — healthcheck

- [ ] **CLI standalone** :
  - [ ] `piighost detect "texte"` — détection PII
  - [ ] `piighost anonymize "texte"` — anonymisation
  - [ ] `cat file.txt | piighost anonymize` — support stdin/pipe
  - [ ] Options : `--strategy`, `--labels`, `--format json|text`

## Priorité basse

- [ ] **Support multilingue explicite** :
  - [ ] Configuration de langue (`language` param)
  - [ ] Patterns regex localisés (téléphone, code postal par pays)
  - [ ] Documentation des langues supportées par GLiNER2

- [ ] **Traitement de fichiers** :
  - [ ] DOCX
  - [ ] PDF
  - [ ] CSV (anonymisation par colonne)
  - [ ] JSON structuré (anonymisation par chemin JSONPath)

- [ ] **Métriques Prometheus** :
  - [ ] `piighost_entities_detected_total` (counter, par type)
  - [ ] `piighost_anonymization_duration_seconds` (histogram)
  - [ ] `piighost_cache_hits_total` / `piighost_cache_misses_total`

- [ ] **Rate limiting intégré** :
  - [ ] Middleware FastAPI avec limites configurables
  - [ ] Headers `X-RateLimit-*`

- [ ] **Détection sémantique LLM** :
  - [ ] `LLMDetector` utilisant un modèle local (Ollama) pour détecter du PII contextuel
  - [ ] Utile pour PII obfusqué, imbriqué, ou dans du texte informel