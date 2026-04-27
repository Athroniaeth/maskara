I've been building agents on top of LangGraph for a while now, and I keep running into the same problem: every message sent to the LLM might contain sensitive data, and depending on the provider you're using, what happens to that data changes completely.

To simplify, there are three families of providers:

- **Non-EU cloud** (OpenAI, Anthropic, Google): the best models, but data leaves the EU, which is problematic on many fronts. I wrote a summary [here](https://athroniaeth.github.io/piighost/why-anonymize/#how-a-cloud-llm-works).
- **Sovereign EU cloud** (Mistral, Aleph Alpha): processing happens in the EU, but a more restricted catalog.
- **Self-hosted** (Ollama, vLLM, open-weight models): you never hand your data to a third party, you control everything, but you have to manage the infrastructure yourself.

I'm currently working on notarial documents, which in practice limits me to Mistral. So I can't take advantage of the best LLMs to do my work. The only clean way to decouple the LLM from the sensitivity of the content is to anonymize upstream.

## Why it's harder than it looks

On paper, it's simple. You take a detector (regex for emails, NER model for names), replace what matches with placeholders, and send to the LLM.

In practice, four problems show up almost immediately.

**Placeholder consistency.** The point of anonymization is to replace "Patrick" with a placeholder like `<<PERSON:1>>`, which tells the LLM two things. A person has been hidden here, and every occurrence of `<<PERSON:1>>` refers to the same person. If "Patrick" becomes `<<PERSON:1>>` at the start of the text and `<<PERSON:3>>` at the end, the LLM can no longer reason about the fact that it's the same individual.

**Variants missed by the detector.** The NER detects "Patrick Dupont" at the start of the text but misses "Patrick" alone two sentences later. Or it detects "Patrick" but not "patrick" in lowercase. Or not "Patriick" with a typo.

**Overlap between detectors.** You chain two NERs to boost recall. On "Patrick", both can claim the same span with different labels (one says `PERSON`, the other says `ORG` because it confused it with a company name). Without arbitration, the final replacement hits the same position twice and breaks the text.

**Persistence across messages.** Once the LLM has seen `<<PERSON:1>>` in message 1, message 2 needs to use the same placeholder. Without shared memory, "Patrick" becomes `<<PERSON:1>>` then `<<PERSON:7>>` depending on the moment, and the LLM loses track.

And that's before we even get to the agent, where tools need to receive the real values (to send an email, for example) while the LLM should only see placeholders. On the front-end side, you also have to deanonymize the placeholders before showing the response to the user, without the LLM ever knowing the mapping.

It's to address all of this that I built **PIIGhost**, an open-source project that adds a layer of detection, anonymization and deanonymization on top of your detectors (NER, regex, LLM, whatever you want). It also offers a conversational mode and a LangChain middleware that plugs into LangGraph without modifying your existing code.

The rest of the article follows the pipeline order: detection, span arbitration, entity linking, merging, anonymization, then the conversational and agent layers.

---

## Step 1: Detection

Everything starts with detection. A detector takes text and returns a list of `Detection` objects (text found, label, position, confidence). PIIGhost ships several out of the box:

- `RegexDetector` for structured formats (emails, phone numbers, IBAN).
- `ExactMatchDetector` for fixed words known in advance, useful for tests or business dictionaries.
- `Gliner2Detector` for NER, plugged on GLiNER2 by default.
- `CompositeDetector` to combine multiple detectors into one.

The interface is an `AnyDetector` protocol, so you can plug in your own (an LLM call, another NER model, whatever you want).

Here's an example without an ML model, just to show the mechanics:

```python
from piighost import ExactMatchDetector

detector = ExactMatchDetector([
    ("Patrick", "PERSON"),
    ("Paris", "LOCATION"),
])

detections = await detector.detect("Patrick lives in Paris.")
# Detection(text='Patrick', label='PERSON',   position=Span(0, 7),   confidence=1.0)
# Detection(text='Paris',   label='LOCATION', position=Span(15, 20), confidence=1.0)
```

At this stage, we have a raw list of detections. No anonymization, no duplicate handling, nothing. Just "here's what looks like PII and where it sits".

---

## Step 2: Span arbitration

First real problem. When you chain multiple detectors on the same text, they can claim the same chunk with different labels. This is typically what happens when you combine two NERs to boost recall. They step on each other and one of them is wrong.

A concrete example. On the following sentence:

> "Patrick works at Orange since 2015."

You run two NERs:

- NER A (a generalist model) detects "Patrick" → `PERSON`, span `[0:7]`, confidence `0.95`
- NER B (a domain model less reliable on first names) detects "Patrick" → `ORG`, span `[0:7]`, confidence `0.60` (it confused it with a company name)

Both point to exactly the same span `[0:7]`, but with mutually exclusive labels. If we replace both, we hit the same position twice and end up with something broken like `<<ORG:1>><<PERSON:1>> works at...`. We have to choose.

That's the role of the **span resolver**. PIIGhost ships two by default:

- `ConfidenceSpanConflictResolver`: keeps the detection with the highest confidence in case of overlap. The reasonable default.
- `DisabledSpanConflictResolver`: does nothing, to use if your detections are already clean or if you want to handle the case yourself.

You can also write your own (prefer the longest span, prefer a specific label, etc.) by implementing the `SpanConflictResolver` protocol.

```python
from piighost import ConfidenceSpanConflictResolver

resolver = ConfidenceSpanConflictResolver()
clean = resolver.resolve(detections)

# Input detections:
#   - PERSON "Patrick" [0:7] confidence=0.95   (NER A)
#   - ORG    "Patrick" [0:7] confidence=0.60   (NER B)
#
# After resolution, only this remains:
#   - PERSON "Patrick" [0:7] confidence=0.95
```

At the end of this step, no more overlaps. Each chunk of text is claimed by only one detection.

> Overlap isn't necessarily exact. The resolver also handles cases where one span is included in another, or where two spans partially overlap. The principle stays the same. Keep the most confident.

---

## Step 3: Entity linking

Second problem. The NER misses occurrences. It finds "Patrick Dupont" in sentence 1 but misses "Patrick" alone in sentence 3. If we stop at raw detection, "Patrick" stays in clear text in the anonymized output. That's exactly what we want to avoid.

The **linker** fixes this. `ExactEntityLinker` does two things:

1. For each detection, it searches for all other occurrences of the same text in the document, using a word-boundary regex (to avoid matching "Patric" inside "Patricia").
2. It groups every detection that points to the same normalized text into a single `Entity` object.

Concretely:

```text
Text: "Patrick Dupont lives in Paris. Patrick loves Paris."

Raw NER detections:
  - PERSON   "Patrick Dupont"  (sentence 1)
  - LOCATION "Paris"            (sentence 1)
  # "Patrick" and "Paris" in sentence 2 were missed by the NER

After ExactEntityLinker:
  - Entity(label=PERSON,   detections=["Patrick Dupont", "Patrick"])
  - Entity(label=LOCATION, detections=["Paris", "Paris"])
```

All occurrences are recovered, grouped by entity. The NER misses things, the linker catches them.

> One caveat. The linker does exact string matching. It won't catch "patrick" in lowercase or "Patriick" with a typo. For that, you need a fuzzy linker, which you can write by implementing the `EntityLinker` protocol.

---

## Step 4: Entity merging

Third problem, more subtle. Imagine two detectors that see the same person but with different spans:

- The NER detects "Patrick Dupont" → entity A, label `PERSON`
- A business dictionary detects "Patrick" alone (because they're in the firm's associates list) → entity B, label `PERSON`

After the linker, you end up with two distinct entities even though it's clearly the same person. If you anonymize as is, "Patrick Dupont" becomes `<<PERSON:1>>` and "Patrick" alone becomes `<<PERSON:2>>`. The LLM thinks these are two different people.

The **entity resolver** merges these duplicates. Two options:

- `MergeEntityConflictResolver`: uses union-find to merge entities sharing at least one detection (strict matching). The default.
- `FuzzyEntityConflictResolver`: uses Jaro-Winkler distance to merge entities whose canonical text is close (e.g. "Patrick" and "Patriick" with a typo). More tolerant, but higher false-positive risk.

A concrete example:

```text
Before merge:
  - Entity(label=PERSON, detections=["Patrick Dupont"])
  - Entity(label=PERSON, detections=["Patrick"])
  # Both entities share a detection on the string "Patrick"

After MergeEntityConflictResolver:
  - Entity(label=PERSON, detections=["Patrick Dupont", "Patrick"])
```

At this stage, you have a clean list of entities, each grouping all of its occurrences. No more duplicates, no more overlaps.

---

## Step 5: Anonymization

Now we can replace. The `Anonymizer` generates a unique placeholder per entity via a `PlaceholderFactory`, then replaces the spans in the text from right to left (so the positions of the following spans don't shift).

```python
from piighost import Anonymizer, LabelCounterPlaceholderFactory

anonymizer = Anonymizer(LabelCounterPlaceholderFactory())
result = anonymizer.anonymize(text, entities)

# Patrick Dupont lives in Paris. Patrick loves Paris.
# becomes
# <<PERSON:1>> lives in <<LOCATION:1>>. <<PERSON:1>> loves <<LOCATION:1>>.
```

Several factories are provided, to choose based on your case:

- `LabelCounterPlaceholderFactory`: `<<PERSON:1>>`, `<<LOCATION:1>>`. Readable in logs and traces.
- `LabelHashPlaceholderFactory`: `<<PERSON:a3f9>>`. Avoids leaking the order in which entities appear from one conversation to another.
- `FakerCounterPlaceholderFactory`: "John Smith", "Springfield". Preserves linguistic flow for the LLM (useful if the model struggles with raw placeholders).
- `MaskPlaceholderFactory`: `[REDACTED]`. Pure anonymization, irreversible.

The default `<<LABEL:N>>` format has four useful properties:

- it's unique as a token in theory,
- the LLM immediately sees what type of PII it's dealing with,
- it's not ambiguous in regular text,
- it can't be confused with another placeholder (unlike a plain `<<PERSON>>`, which doesn't distinguish people from one another).

---

## The assembled pipeline

All the steps above chain together into a pipeline:

```python
from piighost.pipeline import AnonymizationPipeline
from piighost import (
    ConfidenceSpanConflictResolver,
    ExactEntityLinker,
    MergeEntityConflictResolver,
    Anonymizer,
    LabelCounterPlaceholderFactory,
)

pipeline = AnonymizationPipeline(
    detector=detector,
    span_resolver=ConfidenceSpanConflictResolver(),
    entity_linker=ExactEntityLinker(),
    entity_resolver=MergeEntityConflictResolver(),
    anonymizer=Anonymizer(LabelCounterPlaceholderFactory()),
)

anonymized, entities = await pipeline.anonymize(
    "Patrick Dupont lives in Paris. Patrick loves Paris."
)
# <<PERSON:1>> lives in <<LOCATION:1>>. <<PERSON:1>> loves <<LOCATION:1>>.

original, _ = await pipeline.deanonymize(anonymized)
# Patrick Dupont lives in Paris. Patrick loves Paris.
```

The pipeline keeps a cache of the mapping (SHA-256 key on the input text), so deanonymization is free after the first call.

---

## The conversation problem

All of this works for an isolated message. In a real conversation, it breaks because of three problems.

**Counters not shared.** Every call to `anonymize` starts from scratch. The `Patrick → <<PERSON:1>>` mapping from message 1 is not guaranteed to be reused at message 2.

**Detections missed across messages.** The NER detects "Patrick" in message 1 but misses it in message 5. Without memory of entities already seen, we can't fill the gap.

**Concurrent conversations.** If multiple users share the same pipeline instance, their entities mix together. The `<<PERSON:1>>` of one and the other become indistinguishable.

Bug demonstration:

```python
# Message 1
m1, _ = await pipeline.anonymize("Patrick lives in Paris.")
# <<PERSON:1>> lives in <<LOCATION:1>>.

# Message 2, state not shared
m2, _ = await pipeline.anonymize("Bob is happy.")
# <<PERSON:1>> is happy.   ← the counter restarted at 1
# Bob inherits the same placeholder as Patrick → collision:
# the LLM thinks it's the same person.
```

`ThreadAnonymizationPipeline` extends the standard pipeline with a `ConversationMemory` scoped by `thread_id`. The memory accumulates entities across messages, deduplicated by `(text.lower(), label)`. Each call passes a `thread_id`, and the cache is prefixed with that identifier so conversations stay isolated.

```python
from piighost.pipeline.thread import ThreadAnonymizationPipeline

pipeline = ThreadAnonymizationPipeline(detector=..., span_resolver=..., ...)

# Conversation A
m1, _ = await pipeline.anonymize("Patrick lives in Paris.", thread_id="user-A")
# <<PERSON:1>> lives in <<LOCATION:1>>.

m2, _ = await pipeline.anonymize("Patrick is happy.", thread_id="user-A")
# <<PERSON:1>> is happy.   ← guaranteed, shared via the thread memory

# Conversation B in parallel, isolated
m3, _ = await pipeline.anonymize("Bob loves Lyon.", thread_id="user-B")
# <<PERSON:1>> loves <<LOCATION:1>>.   ← counter independent from conversation A
```

`ThreadAnonymizationPipeline` also adds two operations useful for the agent case:

- `anonymize_with_ent(text, thread_id=...)`: pure string replacement, without detection. Uses the entities already known to the thread to anonymize a new text. Faster, but doesn't detect new PII.
- `deanonymize_with_ent(text, thread_id=...)`: inverse replacement. Useful when the LLM produces text with placeholders we want to restore.

These two operations correctly handle cases where one placeholder is a prefix of another (`<<PERSON:1>>` vs `<<PERSON:10>>`) by replacing the longer ones first.

---

## The agent problem

In a LangGraph agent, the LLM doesn't just process messages. It calls tools, reads their results, and reasons in a loop. Anonymizing properly in this setting requires three interventions at precise moments.

**Before the LLM call.** All messages have to be anonymized. This is the standard `pipeline.anonymize()`, applied to each message of the context.

**Before and after a tool execution.** The LLM calls `send_email(to=<<PERSON:1>>)`. The tool needs the real address, not the placeholder. We deanonymize the arguments via `deanonymize_with_ent`, execute, then re-anonymize the result before handing it back to the LLM.

**Before display to the user.** The LLM produces "Done, I sent the email to `<<PERSON:1>>`". The user wants to see "Patrick", not the placeholder.

`PIIAnonymizationMiddleware` wires these three hooks into LangGraph:

```python
from langchain.agents import create_agent
from piighost.middleware import PIIAnonymizationMiddleware

middleware = PIIAnonymizationMiddleware(pipeline=pipeline)

agent = create_agent(
    model="mistral:mistral-large-latest",
    tools=[send_email, get_weather],
    middleware=[middleware],
)
```

Under the hood, the middleware reads the `thread_id` from the LangGraph config (`get_config()["configurable"]["thread_id"]`) and passes it to every pipeline operation. The LLM never sees real values, the tools receive them normally, the user gets the response with their names intact. No agent code to modify.

---

## piighost-chat: the human-in-the-loop demo

To make all of this concrete, I built a chatbot on top of the library. The user sees what is about to be anonymized before the message is sent to the LLM. They can deselect a span flagged by mistake, or select text the detector missed. Once validated, the message goes into the pipeline.

![piighost-chat application](https://dev-to-uploads.s3.amazonaws.com/uploads/articles/pac3ix2cnjrdi9y8si31.png)


This kind of human-in-the-loop UX is what makes auto-anonymization actually usable in real workflows, where automatic precision often plateaus around 90-95% and those few missed percent can be a problem. The auto pass does the heavy lifting, the human catches the edges.

For instance, here you type your message, it goes through the piighost API and the front shows what was detected and what's about to be anonymized.

![Automatic PII detection before sending to the LLM](https://dev-to-uploads.s3.amazonaws.com/uploads/articles/0zji4sbp1pwcsg2l43rs.png)

You can remove anonymized entities if there's a false positive.

![Manual removal of a false positive](https://dev-to-uploads.s3.amazonaws.com/uploads/articles/7i5u9da5v7t63qlsnop9.png)

You can also select text to add new entities to anonymize.

![Manual selection of a PII missed by the detector](https://dev-to-uploads.s3.amazonaws.com/uploads/articles/heaxmgmlhpxuu3s8ns5f.png)

![The added entity appears in the list of anonymized PII](https://dev-to-uploads.s3.amazonaws.com/uploads/articles/e5n1ni84nrudib57wtql.png)

If you ask for information about an anonymized PII, for instance which letter the word starts with, the LLM won't be able to answer.

![The LLM, seeing only the placeholder, can't answer about the actual content](https://dev-to-uploads.s3.amazonaws.com/uploads/articles/a4eccg4abdie2bu7685a.png)

---

The library is in its early days. I tried to anticipate as many cases as possible starting from my own needs on notarial documents, but I know that's a particular angle and that many things can be debated. Components that aren't generic enough, abstractions that don't pull their weight, use cases I haven't seen.
If you give it a try, your feedback genuinely matters to me:

what felt missing or counter-intuitive,
what feels too complex or pointless and should be removed,
the use cases where it doesn't hold up.

Anything is welcome, whether through a GitHub issue, a PR, or even a direct message. I'd rather cut early on what doesn't belong than accumulate debt.

- [piighost](https://github.com/Athroniaeth/piighost)
- [piighost-chat](https://github.com/Athroniaeth/piighost-chat)
- [Documentation](https://athroniaeth.github.io/piighost/)

Thanks for reading.
