---
icon: lucide/shield-check
---

# Reference Middleware

Module: `piighost.middleware`

---

## `PIIAnonymizationMiddleware`

LangChain middleware that transparently anonymizes personal data around the LLM / tools boundary.

Extends `AgentMiddleware` from LangChain and intercepts the agent loop at **3 points**:

| Hook | When | Operation |
|------|------|-----------|
| `abefore_model` | Before each LLM call | Anonymizes all messages |
| `aafter_model` | After each LLM response | Deanonymizes for the user |
| `awrap_tool_call` | Around each tool | Deanonymizes args, reanonymizes response |

### Constructor

```python
PIIAnonymizationMiddleware(pipeline: ConversationAnonymizationPipeline)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `pipeline` | `ConversationAnonymizationPipeline` | Configured conversation pipeline with memory |

### Usage

```python
from piighost.middleware import PIIAnonymizationMiddleware
from piighost.conversation_pipeline import ConversationAnonymizationPipeline
from langchain.agents import create_agent

middleware = PIIAnonymizationMiddleware(pipeline=conv_pipeline)

agent = create_agent(
    model="openai:gpt-4o-mini",
    tools=[...],
    middleware=[middleware],
)
```

---

## Hooks in detail

### `abefore_model(state, runtime) -> dict | None` *(async)*

Called before each LLM call. Anonymizes all messages in the conversation via `pipeline.anonymize()`.

**Behavior by message type:**

- `HumanMessage` → full NER detection and anonymization
- `AIMessage` → anonymization (re-anonymizes any deanonymized values)
- `ToolMessage` → anonymization (re-anonymizes tool responses)

```python
# Before abefore_model:
# [HumanMessage("Send an email to Patrick in Paris")]

# After abefore_model:
# [HumanMessage("Send an email to <<PERSON_1>> in <<LOCATION_1>>")]
```

**Returns**: `{"messages": [...]}` if modifications were made, `None` otherwise.

---

### `aafter_model(state, runtime) -> dict | None` *(async)*

Called after each LLM response. Deanonymizes all messages so the user sees real values. First tries `pipeline.deanonymize()` (cache-based), falls back to `pipeline.deanonymize_with_ent()` (entity-based) on `CacheMissError`.

```python
# Before aafter_model:
# [AIMessage("Done! Email sent to <<PERSON_1>>.")]

# After aafter_model:
# [AIMessage("Done! Email sent to Patrick.")]
```

**Returns**: `{"messages": [...]}` if modifications were made, `None` otherwise.

---

### `awrap_tool_call(request, handler) -> ToolMessage | Command` *(async)*

Wraps each tool call in 3 steps:

1. **Deanonymizes** `str` arguments → the tool receives real values
2. **Executes** the tool via `handler(request)`
3. **Reanonymizes** the tool response via `pipeline.anonymize()` → the LLM never sees personal data

```python
# LLM calls : send_email(to="<<PERSON_1>>", subject="Hello")
#                      ↓  deanonymize args
# Tool gets  : send_email(to="Patrick", subject="Hello")
# Tool returns: "Email successfully sent to Patrick."
#                      ↓  reanonymize response
# LLM sees   : "Email successfully sent to <<PERSON_1>>."
```

Only `str` arguments are deanonymized. Non-string types are passed through unchanged.

---

## Full flow

```mermaid
sequenceDiagram
    participant U as User
    participant M as PIIAnonymizationMiddleware
    participant L as LLM
    participant T as Tool

    U->>M: User message (plain text)
    M->>M: abefore_model()<br/>anonymize HumanMessage via NER
    M->>L: Anonymized message (placeholders)
    L->>M: Tool call with anonymized args
    M->>M: awrap_tool_call()<br/>deanonymize args
    M->>T: Tool call with real values
    T->>M: Tool response (real values)
    M->>M: awrap_tool_call()<br/>reanonymize response
    M->>L: Anonymized tool response
    L->>M: Final response (placeholders)
    M->>M: aafter_model()<br/>deanonymize for user
    M->>U: Final response (plain text)
```

---

## LangChain dependency

`PIIAnonymizationMiddleware` requires `langchain` to be installed. If not, an `ImportError` is raised on import:

```
ImportError: You must install piighost[langchain] for use middleware
```

Installation:

```bash
uv add piighost langchain langgraph
```

---

## Full example

```python
import asyncio
from gliner2 import GLiNER2
from langchain.agents import create_agent
from langchain_core.tools import tool

from piighost.anonymizer import Anonymizer
from piighost.conversation_memory import ConversationMemory
from piighost.conversation_pipeline import ConversationAnonymizationPipeline
from piighost.detector import GlinerDetector
from piighost.entity_linker import ExactEntityLinker
from piighost.entity_resolver import MergeEntityConflictResolver
from piighost.middleware import PIIAnonymizationMiddleware
from piighost.placeholder import CounterPlaceholderFactory
from piighost.span_resolver import ConfidenceSpanConflictResolver

@tool
def get_info(person: str) -> str:
    """Returns information about a person."""
    return f"{person} is a software engineer in Paris."

model = GLiNER2.from_pretrained("urchade/gliner_multi_pii-v1")

pipeline = ConversationAnonymizationPipeline(
    detector=GlinerDetector(model=model, labels=["PERSON", "LOCATION"], threshold=0.5),
    span_resolver=ConfidenceSpanConflictResolver(),
    entity_linker=ExactEntityLinker(),
    entity_resolver=MergeEntityConflictResolver(),
    anonymizer=Anonymizer(CounterPlaceholderFactory()),
    memory=ConversationMemory(),
)
middleware = PIIAnonymizationMiddleware(pipeline=pipeline)

agent = create_agent(
    model="openai:gpt-4o-mini",
    system_prompt="You are a helpful assistant. Treat placeholders as real values.",
    tools=[get_info],
    middleware=[middleware],
)

async def main():
    result = await agent.ainvoke({
        "messages": [{"role": "user", "content": "Who is Patrick?"}]
    })
    print(result["messages"][-1].content)

asyncio.run(main())
```
