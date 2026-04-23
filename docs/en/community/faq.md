---
icon: lucide/message-circle-question
---

# FAQ

??? question "Do my placeholders have to look like `<<PERSON_1>>`?"
    No. The format is driven by `AnyPlaceholderFactory`. By default `CounterPlaceholderFactory` produces `<<LABEL_N>>`, but `HashPlaceholderFactory` yields opaque deterministic tags, `RedactPlaceholderFactory` produces `<LABEL>` without a counter, and you can write your own factory. See [Extending PIIGhost](../extending.md).

??? question "Does the LLM see raw PII when it calls a tool?"
    No. The middleware deanonymizes arguments right before the tool executes, then re-anonymizes the tool response before it flows back to the LLM. The tool sees real values; the LLM only sees placeholders. See the sequence diagram in [Architecture](../architecture.md).

??? question "What happens if the LLM hallucinates a PII that was not in the input?"
    It is **not** anonymized by `piighost`: entity linking works on detections coming from the input, not on invented values. To cover that case, add a post-response detection pass at the application layer. See [Limitations](../limitations.md).

??? question "Is the cache shared across threads or conversations?"
    No. The `aiocache` cache is scoped by `thread_id`. Two parallel conversations never see each other's placeholders, preventing cross-user leaks. The `thread_id` is extracted automatically from the LangGraph config.

??? question "Can I use `piighost` without LangChain?"
    Yes. `AnonymizationPipeline` and `ThreadAnonymizationPipeline` are usable standalone, without the middleware. See [Basic usage](../examples/basic.md).

??? question "Does `piighost` encrypt cached data?"
    No. The cache stores the `placeholder → value` mapping in memory (or in the `aiocache` backend you configured). See [Security](../security.md) for the full list of things out of scope.
