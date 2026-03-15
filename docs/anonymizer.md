---
title: Anonymizer Reference API
---

# Anonymizer

`src/maskara/anonymizer.py`

Pipeline d'anonymisation en trois etapes : detection NER via GLiNER2, assignation de placeholders, et remplacement dans le texte. Concu pour etre utilise directement ou via un middleware.

---

## `Anonymizer`

```python
class Anonymizer:
    def __init__(
        self,
        extractor: GLiNER2,
        entity_types: list[str] | None = None,
        min_confidence: float = 0.5,
    )
```

| Parametre | Defaut | Description |
|-----------|--------|-------------|
| `extractor` | | Instance GLiNER2 (ex: `GLiNER2.from_pretrained("fastino/gliner2-base-v1")`) |
| `entity_types` | `["company", "person", "product", "location"]` | Labels a detecter |
| `min_confidence` | `0.5` | Seuil de confiance les entites en dessous sont ignorees |

**Attributs internes :**

| Attribut | Type | Role |
|----------|------|------|
| `_thread_store` | `dict[str, dict[str, str]]` | Mapping `thread_id → vocab` pour la coherence multi-tours |

---

## Methodes publiques

### `anonymize(text, thread_id)`

```python
def anonymize(
    self,
    text: str,
    thread_id: str | None = None,
) -> tuple[str, dict[str, str]]
```

Anonymise le texte et retourne le resultat avec le vocabulaire utilise.

**Parametres :**

| Parametre | Description |
|-----------|-------------|
| `text` | Texte a anonymiser |
| `thread_id` | Identifiant de conversation. Si `None`, un UUID est genere (pas de reutilisation inter-tours). |

**Retourne :** `(texte_anonymise, vocab)` ou `vocab` est un `dict[str, str]` mappant chaque texte original vers son placeholder.

```python
extractor = GLiNER2.from_pretrained("fastino/gliner2-base-v1")
anonymizer = Anonymizer(extractor)

text = "Apple Inc. CEO Tim Cook a annonce iPhone 15 a Cupertino."
anon, vocab = anonymizer.anonymize(text, thread_id="conv-1")

print(anon)
# "<COMPANY_1> CEO <PERSON_1> a annonce <PRODUCT_1> a <LOCATION_1>."

print(vocab)
# {"Apple Inc.": "<COMPANY_1>", "Tim Cook": "<PERSON_1>",
#  "iPhone 15": "<PRODUCT_1>", "Cupertino": "<LOCATION_1>"}
```

---

### `deanonymize(text, vocab)`

```python
def deanonymize(self, text: str, vocab: dict[str, str]) -> str
```

Restaure les valeurs originales dans le texte anonymise.

**Parametres :**

| Parametre | Description |
|-----------|-------------|
| `text` | Texte contenant des placeholders |
| `vocab` | Mapping `texte_original → placeholder` (tel que retourne par `anonymize`) |

```python
original = anonymizer.deanonymize(anon, vocab)
print(original)
# "Apple Inc. CEO Tim Cook a annonce iPhone 15 a Cupertino."
```

---

### `anonymize_messages(messages, thread_id)`

```python
def anonymize_messages(
    self,
    messages: list[AnyMessage],
    thread_id: str | None = None,
) -> tuple[list[AnyMessage], dict[str, str]]
```

Anonymise une liste de messages LangChain. Le `thread_id` est partage entre tous les messages pour maintenir la coherence du vocabulaire.

**Retourne :** `(messages_anonymises, vocab_combine)` le vocab combine contient toutes les entites de tous les messages.

```python
from langchain_core.messages import HumanMessage

messages = [HumanMessage(content="Pierre habite a Lyon")]
anon_msgs, vocab = anonymizer.anonymize_messages(messages, thread_id="conv-1")

print(anon_msgs[0].content)
# "<PERSON_1> habite a <LOCATION_1>"
```

---

### `deanonymize_messages(messages, thread_id, placeholders)`

```python
def deanonymize_messages(
    self,
    messages: list[AnyMessage],
    thread_id: str | None = None,
    placeholders: dict[str, str] | None = None,
) -> list[AnyMessage]
```

Desanonymise une liste de messages. Deux modes :

1. **`placeholders` fourni** : utilise ce vocab directement
2. **`thread_id` fourni** : charge le vocab depuis le `_thread_store`

Si aucun des deux n'est fourni, aucun remplacement n'est effectue.

```python
# Mode thread_id (recommande dans un flux conversationnel)
restored = anonymizer.deanonymize_messages(anon_msgs, thread_id="conv-1")

# Mode explicite (utile pour du one-shot)
restored = anonymizer.deanonymize_messages(anon_msgs, placeholders=vocab)
```

---

## Methodes internes

### `_detect(text)`

```python
def _detect(self, text: str) -> list[tuple[str, str]]
```

Appelle GLiNER2 et retourne les entites detectees sous forme de tuples `(texte, entity_type)`. Filtre par `min_confidence` et strippe le whitespace.

---

### `_assign(detections, vocab)`

```python
def _assign(self, detections: list[tuple[str, str]], vocab: dict[str, str]) -> None
```

Assigne un placeholder a chaque entite pas encore dans `vocab`. Mutation in-place. Trouve le prochain index libre par type en parsant les placeholders existants.

---

### `_replace(text, mapping)` (static)

```python
@staticmethod
def _replace(text: str, mapping: dict[str, str]) -> str
```

Remplace toutes les cles du mapping par leurs valeurs, en traitant les cles les plus longues d'abord. Utilise pour l'anonymisation (texte → placeholder) et la desanonymisation (placeholder → texte).

---

## Exemple complet multi-tours

```python
from gliner2 import GLiNER2
from maskara.anonymizer import Anonymizer

extractor = GLiNER2.from_pretrained("fastino/gliner2-base-v1")
anonymizer = Anonymizer(extractor, min_confidence=0.5)

# --- Tour 1 ---
anon1, vocab1 = anonymizer.anonymize(
    "Pierre habite a Lyon. Pierre est souvent a Lyon.",
    thread_id="conv-1",
)
print(anon1)
# "<PERSON_1> habite a <LOCATION_1>. <PERSON_1> est souvent a <LOCATION_1>."
# Note : les deux occurrences de "Pierre" et "Lyon" sont remplacees.

# --- Tour 2 le vocab est reutilise ---
anon2, vocab2 = anonymizer.anonymize(
    "Marie connait Pierre. Elle vit a Bordeaux.",
    thread_id="conv-1",
)
print(anon2)
# "<PERSON_2> connait <PERSON_1>. Elle vit a <LOCATION_2>."
# "Pierre" garde <PERSON_1> (du tour 1).
# "Marie" recoit <PERSON_2>, "Bordeaux" recoit <LOCATION_2>.

# --- Desanonymisation ---
print(anonymizer.deanonymize(anon2, vocab2))
# "Marie connait Pierre. Elle vit a Bordeaux."
```
