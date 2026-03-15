---
title: Anonymizer — Référence API
---

# Anonymizer

`src/aegra/anonymizer.py`

Composant responsable de la détection NER et du remplacement par placeholders. Conçu pour être utilisé directement, indépendamment de toute couche de transport ou d'orchestration.

---

## Types de données

### `GlinerEntity`

```python
class GlinerEntity(TypedDict):
    text: Required[str]
    confidence: NotRequired[float]
    start: NotRequired[int]
    end: NotRequired[int]
```

Dict brut retourné par la bibliothèque GLiNER2.

---

### `NamedEntity`

```python
@dataclass
class NamedEntity:
    text: str
    entity_type: str
    confidence: float
    start: Optional[int] = None
    end: Optional[int] = None
    anon_start: Optional[int] = None
    anon_end: Optional[int] = None
```

Entité enrichie produite par le pipeline d'anonymisation.

| Attribut | Espace de coordonnées | Description |
|----------|----------------------|-------------|
| `text` | — | Surface form brute telle qu'elle apparaît dans le texte source |
| `entity_type` | — | Label de catégorie (`"person"`, `"location"`, etc.) |
| `confidence` | — | Score GLiNER2 ∈ [0, 1] ; `1.0` pour les occurrences ajoutées par `expand_placeholders` |
| `start` / `end` | **texte original** | Offsets caractères (inclusif / exclusif) dans le texte **avant** anonymisation |
| `anon_start` / `anon_end` | **texte anonymisé** | Offsets du placeholder dans le texte **après** anonymisation — calculés par `compute_anonymized_spans` |

!!! note "Deux espaces de coordonnées"
    `start/end` et `anon_start/anon_end` vivent dans des espaces différents. Ne pas les mélanger : les offsets originaux ne sont plus valides dans le texte anonymisé (les placeholders ont une longueur différente des entités d'origine).

---

### `Placeholder`

```python
class Placeholder(str): ...
```

Sous-classe de `str` représentant un jeton d'anonymisation. Format : `<TYPE_N>` — ex. `<PERSON_1>`, `<LOCATION_3>`.

`TYPE` est le label en majuscules, `N` l'index 1-based par type au sein d'un thread.

---

### `ThreadID`

```python
class ThreadID(str): ...
```

Identifiant de fil de conversation. Généré automatiquement via UUID si non fourni.

---

## Fonctions utilitaires

### `build_placeholder(label, index)`

```python
def build_placeholder(label: str, index: int) -> Placeholder
```

```python
build_placeholder("person", 1)   # → "<PERSON_1>"
build_placeholder("location", 3) # → "<LOCATION_3>"
```

---

### `resolve_thread_id(thread_id)`

```python
def resolve_thread_id(thread_id: Optional[str]) -> ThreadID
```

Retourne un `ThreadID`, en générant un UUID si `thread_id` est `None`.

---

## Classe `Anonymizer`

```python
class Anonymizer:
    def __init__(
        self,
        extractor: GLiNER2,
        entity_types: Optional[List[str]] = None,
        min_confidence: float = 0.5,
    )
```

| Paramètre | Défaut | Description |
|-----------|--------|-------------|
| `extractor` | — | Instance GLiNER2 (ex: `GLiNER2.from_pretrained("fastino/gliner2-base-v1")`) |
| `entity_types` | `["company", "person", "product", "location"]` | Labels GLiNER2 à détecter |
| `min_confidence` | `0.5` | Seuil de confiance minimum — les entités en dessous sont ignorées |

---

## Méthodes

### `detect_entities(text)`

```python
def detect_entities(self, text: str) -> List[NamedEntity]
```

Appelle `GLiNER2.extract_entities()` avec les labels configurés, enrichit chaque résultat en `NamedEntity`, puis filtre par `min_confidence`.

**Retourne :** liste de `NamedEntity` avec `start`, `end`, `confidence` renseignés.

**Limite connue :** GLiNER2 ne détecte typiquement que la **première occurrence** d'une entité dans un texte long. Les occurrences suivantes doivent être couvertes par `expand_placeholders`.

---

### `assign_placeholders(detections, existing_vocab)`

```python
def assign_placeholders(
    self,
    detections: List[NamedEntity],
    existing_vocab: Optional[Dict[str, Placeholder]] = None,
) -> Dict[Placeholder, List[NamedEntity]]
```

Assigne un placeholder à chaque surface form unique dans `detections`.

**Règles d'assignation :**

- Deux entités avec le **même texte** → même placeholder
- Deux entités avec des textes différents d'un même type → indices distincts (`<PERSON_1>`, `<PERSON_2>`)
- Si `existing_vocab` est fourni (thread_store du tour précédent) : les surfaces déjà connues réutilisent leur placeholder existant ; les nouveaux indices partent après le maximum déjà utilisé, évitant ainsi les collisions

**Retourne :** `Dict[Placeholder, List[NamedEntity]]`

---

### `expand_placeholders(text, placeholders)`

```python
def expand_placeholders(
    self,
    text: str,
    placeholders: Dict[Placeholder, List[NamedEntity]],
) -> Dict[Placeholder, List[NamedEntity]]
```

Compense la détection partielle de GLiNER2 en balayant le texte original à la recherche de toutes les occurrences de chaque surface détectée.

**Mécanisme :**

Pour chaque placeholder, la référence est `detections[0].text` (la surface telle que GLiNER l'a retournée). Un pattern `re.escape(surface)` est appliqué sur le texte original via `re.finditer`. Les spans déjà connus sont dédupliqués avant ajout. Les nouvelles occurrences reçoivent `confidence=1.0`.

```
Texte   : "Pierre habite à Lyon. Pierre est à Lyon aussi."
GLiNER  : "Pierre" @0   "Lyon" @16         ← premières occurrences uniquement
expand  : "Pierre" @0 @22   "Lyon" @16 @38  ← toutes les occurrences
```

**Extension — variantes et aliases :**

Le matching exact ne couvre pas les variantes (`"Pari"` vs `"Paris"`). Pour les prendre en compte, il faut construire un pattern OR couvrant toutes les surfaces d'une même entité, avec le plus long en premier pour éviter la capture partielle :

```python
surfaces = {"Paris", "Pari"}  # forme canonique + aliases
pattern = "|".join(re.escape(s) for s in sorted(surfaces, key=len, reverse=True))
# → "Paris|Pari"
```

Chaque match crée un `NamedEntity` avec son texte **brut** (pas la forme canonique), ce qui permet à `deanonymize` de restituer la vraie surface d'origine, y compris la variante.

!!! note "Point d'extension"
    Ce mécanisme n'est pas intégré nativement dans `expand_placeholders`. C'est un point d'extension : pour l'activer, il faut fournir un dictionnaire d'aliases et construire le pattern OR manuellement avant d'appeler `re.finditer`. Le point d'intervention dans le code est la boucle sur `placeholders` dans `expand_placeholders`, là où le pattern est actuellement `re.escape(detections[0].text)`.

---

### `replace_with_placeholders(text, placeholders)`

```python
def replace_with_placeholders(
    self,
    text: str,
    placeholders: Dict[Placeholder, List[NamedEntity]],
) -> str
```

Remplace les spans détectés par leurs jetons en préservant la cohérence des offsets.

**Algorithme en deux temps :**

**Temps 1 — sélection greedy des spans à garder :**

1. Collecte tous les candidats `(start, end, placeholder, confidence)`
2. Tri par confiance décroissante, puis par longueur décroissante (un span long et confiant prime sur un court chevauchant)
3. Accepte chaque candidat s'il ne chevauche aucun span déjà accepté

**Temps 2 — remplacement en ordre inverse :**

Les candidats sélectionnés sont triés par `start` **décroissant** et appliqués de droite à gauche :

```
Texte : "Pierre habite à Lyon, Lyon est belle"
        offset: 0      16   20 22   26

① offset 22→26 : "Lyon"   → <LOCATION_1>   (pas d'impact sur offsets 0–21)
② offset 16→20 : "Lyon"   → <LOCATION_1>   (pas d'impact sur offsets 0–15)
③ offset 0→6   : "Pierre" → <PERSON_1>
```

Chaque remplacement ne modifie que le texte **à sa droite**. Les spans restants à traiter sont à des positions **plus petites**, donc leurs offsets ne sont jamais décalés avant leur tour.

!!! danger "Si l'ordre était naturel (gauche → droite)"
    Le remplacement de `"Pierre"` @0–6 par `<PERSON_1>` (10 chars au lieu de 6) décalerait tous les offsets suivants de +4. `"Lyon"` @16 deviendrait introuvable à l'offset 16 — il faudrait recalculer à chaque étape.

---

### `compute_anonymized_spans(anonymized_text, placeholders)`

```python
def compute_anonymized_spans(
    self,
    anonymized_text: str,
    placeholders: Dict[Placeholder, List[NamedEntity]],
) -> Dict[Placeholder, List[NamedEntity]]
```

Calcule `anon_start` / `anon_end` de chaque entité en re-scannant le texte **après** tous les remplacements.

**Pourquoi après coup :** les offsets dans le texte anonymisé dépendent de la taille cumulée de tous les remplacements précédents — ils ne peuvent être connus qu'une fois le texte final produit.

**Association occurrence ↔ entité :** `re.finditer` retourne les occurrences dans l'ordre gauche-droite. Les entités dans `placeholders[placeholder]` sont aussi dans cet ordre (GLiNER d'abord, `expand_placeholders` en ordre croissant de `start`). Le `zip` est donc stable.

---

### `anonymize(text, thread_id)`

```python
def anonymize(
    self,
    text: str,
    thread_id: Optional[str] = None,
) -> tuple[str, Dict[Placeholder, List[NamedEntity]]]
```

Orchestre le pipeline complet : `detect_entities` → `assign_placeholders` → `expand_placeholders` → `replace_with_placeholders` → `compute_anonymized_spans` → mise à jour du `thread_store`.

```python
anon_text, placeholders = anonymizer.anonymize(
    "Tim Cook habite à Cupertino. Tim Cook reviendra à Cupertino.",
    thread_id="thread-001",
)
# GLiNER détecte "Tim Cook" @0 et "Cupertino" @18
# expand_placeholders ajoute "Tim Cook" @31 et "Cupertino" @49
# → "<PERSON_1> habite à <LOCATION_1>. <PERSON_1> reviendra à <LOCATION_1>."
```

**Retourne :** `(texte_anonymisé, placeholders)`

---

### `deanonymize(text, placeholders)`

```python
def deanonymize(
    self,
    text: str,
    placeholders: Dict[Placeholder, List[NamedEntity]],
) -> str
```

Restaure les valeurs originales. Les occurrences multiples d'un même placeholder sont restituées dans l'ordre d'apparition original (tri par `entity.start`), ce qui permet de restituer des surfaces différentes sous un même jeton — utile dans le cas des aliases.

```python
# Avec aliases : "Paris" et "Pari" → <LOCATION_1>
# Les deux NamedEntity gardent leur text brut : "Paris" et "Pari"
# deanonymize restitue chacune à sa place d'origine
```

---

### `anonymize_messages(messages, thread_id)`

```python
def anonymize_messages(
    self,
    messages: list[AnyMessage],
    thread_id: Optional[str] = None,
) -> tuple[list[AnyMessage], Dict[Placeholder, List[NamedEntity]]]
```

Anonymise une liste de messages LangChain en appelant `anonymize` sur le contenu de chacun, en partageant le `thread_id` pour maintenir la cohérence du vocabulaire.

!!! warning
    Seuls les messages dont le `content` est de type `str` sont supportés.

---

### `deanonymize_messages(messages, thread_id, placeholders)`

```python
def deanonymize_messages(
    self,
    messages: list[AnyMessage],
    thread_id: Optional[str] = None,
    placeholders: Optional[Dict[Placeholder, List[NamedEntity]]] = None,
) -> list[AnyMessage]
```

Désanonymise une liste de messages. Priorité : `placeholders` explicites > lookup du `thread_store` par `thread_id`.

---

## Walkthrough bout-en-bout

Les trois mécanismes illustrés sur un seul texte :

```
Texte brut : "Pierre habite à Lyon, Pierre sera à Lyon demain."

── detect_entities ──────────────────────────────────────────
GLiNER détecte : "Pierre" @0   conf=0.91
                 "Lyon"   @16  conf=0.88
(deuxièmes occurrences non détectées)

── assign_placeholders ──────────────────────────────────────
"Pierre" → <PERSON_1>   (index 1 dans type "person")
"Lyon"   → <LOCATION_1> (index 1 dans type "location")

── expand_placeholders ──────────────────────────────────────
re.finditer("Pierre") → @0, @22   (+1 occurrence)
re.finditer("Lyon")   → @16, @38  (+1 occurrence)
Résultat : 4 NamedEntity avec leurs start/end dans le texte original

── replace_with_placeholders ────────────────────────────────
Candidats triés par start décroissant :
  (38, 42) → <LOCATION_1>   texte restant non affecté à gauche
  (22, 28) → <PERSON_1>     texte restant non affecté à gauche
  (16, 20) → <LOCATION_1>   texte restant non affecté à gauche
  (0,  6)  → <PERSON_1>     fin

Résultat : "<PERSON_1> habite à <LOCATION_1>, <PERSON_1> sera à <LOCATION_1> demain."

── compute_anonymized_spans ─────────────────────────────────
re.finditer("<PERSON_1>")   → @0, @22   → anon_start/end sur chaque entité
re.finditer("<LOCATION_1>") → @12, @34  → anon_start/end
(entités triées par start original avant zip pour stabilité)

── thread_store update ──────────────────────────────────────
{"Pierre": <PERSON_1>, "Lyon": <LOCATION_1>}
```

**Sans aliases vs avec aliases dans `expand_placeholders` :**

```
Sans alias : re.finditer("Paris") → trouve "Paris" seulement

Avec alias {"Pari": "Paris"} :
  pattern = "Paris|Pari"  (plus long en premier)
  re.finditer("Paris|Pari") → trouve "Paris" @0 et "Pari" @20
  NamedEntity text="Paris" @0   → <LOCATION_1>
  NamedEntity text="Pari"  @20  → <LOCATION_1>
  deanonymize : <LOCATION_1>@0 → "Paris", <LOCATION_1>@8 → "Pari"
```

---

## Exemple complet

```python
from gliner2 import GLiNER2
from maskara.anonymizer import Anonymizer

extractor = GLiNER2.from_pretrained("fastino/gliner2-base-v1")
anonymizer = Anonymizer(extractor, min_confidence=0.5)

# --- Tour 1 ---
text1 = "Pierre habite à Lyon. Pierre est souvent à Lyon."
anon1, ph1 = anonymizer.anonymize(text1, thread_id="conv-1")
# GLiNER détecte "Pierre" @0, "Lyon" @16
# expand ajoute "Pierre" @22, "Lyon" @37
# → "<PERSON_1> habite à <LOCATION_1>. <PERSON_1> est souvent à <LOCATION_1>."
print(anon1)

# --- Tour 2 — réutilisation du vocabulaire ---
text2 = "Pierre est-il encore à Lyon ?"
anon2, ph2 = anonymizer.anonymize(text2, thread_id="conv-1")
# existing_vocab = {"Pierre": <PERSON_1>, "Lyon": <LOCATION_1>}
# assign_placeholders réutilise les placeholders sans appel GLiNER
# → "<PERSON_1> est-il encore à <LOCATION_1> ?"
print(anon2)

# --- Désanonymisation ---
original1 = anonymizer.deanonymize(anon1, ph1)
# → "Pierre habite à Lyon. Pierre est souvent à Lyon."
print(original1)
```
