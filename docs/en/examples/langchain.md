---
icon: lucide/link
---

# LangChain integration

This page shows the complete integration of PIIGhost into a LangGraph agent, based on the example available in [`examples/graph/`](https://github.com/Athroniaeth/piighost/tree/main/examples/graph).

---

## Installation

To use the LangChain middleware, install the additional dependencies:

=== "uv"

    ```bash
    uv add piighost[langchain] langchain-openai
    ```

=== "pip"

    ```bash
    pip install piighost langchain langgraph langchain-openai
    ```

!!! warning "Optional dependency"
    `PIIAnonymizationMiddleware` imports `langchain` when instantiated. If `langchain` is not installed, an explicit `ImportError` is raised: `"You must install piighost[langchain] for use middleware"`.

---

## Integration structure

```mermaid
flowchart TB
    classDef model fill:#A5D6A7,stroke:#2E7D32,color:#000
    classDef comp fill:#90CAF9,stroke:#1565C0,color:#000
    classDef mw fill:#BBDEFB,stroke:#1565C0,color:#000
    classDef agent fill:#FFF9C4,stroke:#F9A825,color:#000

    MODEL["`**GLiNER2 model**
    _fastino/gliner2-multi-v1_`"]:::model
    DET["`**Gliner2Detector**
    _wraps the NER model_`"]:::comp
    PIPE["`**ThreadAnonymizationPipeline**
    _extends AnonymizationPipeline_
    _holds ConversationMemory_`"]:::comp
    MW["`**PIIAnonymizationMiddleware**
    _LangChain hooks_`"]:::mw
    AGENT["`**create_agent(middleware=[...])**
    _LangGraph entry point_`"]:::agent

    MODEL -->|wrapped by| DET
    DET -->|injected into| PIPE
    PIPE -->|passed to| MW
    MW -->|registered with| AGENT
```

---

## Full example

```python
from dotenv import load_dotenv
from gliner2 import GLiNER2
from langchain.agents import create_agent
from langchain_core.tools import tool

from piighost.anonymizer import Anonymizer
from piighost.detector.gliner2 import Gliner2Detector
from piighost.linker.entity import ExactEntityLinker
from piighost.resolver import MergeEntityConflictResolver, ConfidenceSpanConflictResolver
from piighost.middleware import PIIAnonymizationMiddleware
from piighost.pipeline import ThreadAnonymizationPipeline
from piighost.placeholder import CounterPlaceholderFactory

load_dotenv()


# ---------------------------------------------------------------------------
# 1. Define the agent tools
# ---------------------------------------------------------------------------

@tool
def send_email(to: str, subject: str, body: str) -> str:
    """Send an email to the given address.

    Args:
        to: Recipient email address.
        subject: Email subject line.
        body: Email body text.

    Returns:
        Confirmation string.
    """
    return f"Email successfully sent to {to}."


@tool
def get_weather(country_or_city: str) -> str:
    """Get the current weather for a given location.

    Args:
        country_or_city: Name of the city or country.

    Returns:
        A weather summary string.
    """
    return f"The weather in {country_or_city} is 22C and sunny."


# ---------------------------------------------------------------------------
# 2. Configure the system prompt for placeholders
# ---------------------------------------------------------------------------

system_prompt = """\
You are a helpful assistant. Some inputs may contain anonymized placeholders \
that replace real values for privacy reasons.

Rules:
1. Treat every placeholder as if it were the real value. Never comment on its \
format, never say it is a token, never ask the user to reveal it.
2. Placeholders can be passed directly to tools use them as-is as input arguments. \
This preserves the user's privacy while still allowing tools to operate.
3. If the user asks for a specific detail about a placeholder \
(e.g. "what is the first letter?"), reply briefly: "I cannot answer that question \
as the data has been anonymized to protect your personal information."
"""

# ---------------------------------------------------------------------------
# 3. Initialize the anonymization stack
# ---------------------------------------------------------------------------

# Load the GLiNER2 model (HuggingFace download ~500 MB on first run)
extractor = GLiNER2.from_pretrained("fastino/gliner2-multi-v1")

entity_linker = ExactEntityLinker()
entity_resolver = MergeEntityConflictResolver()
span_resolver = ConfidenceSpanConflictResolver()

ph_factory = CounterPlaceholderFactory()
anonymizer = Anonymizer(ph_factory=ph_factory)

detector = Gliner2Detector(
    model=extractor,
    threshold=0.5,
    labels=["PERSON", "LOCATION"],
)
pipeline = ThreadAnonymizationPipeline(
    detector=detector,
    span_resolver=span_resolver,
    entity_linker=entity_linker,
    entity_resolver=entity_resolver,
    anonymizer=anonymizer,
)
middleware = PIIAnonymizationMiddleware(pipeline=pipeline)

# ---------------------------------------------------------------------------
# 4. Create the LangGraph agent with the middleware
# ---------------------------------------------------------------------------

graph = create_agent(
    model="openai:gpt-5.4",
    system_prompt=system_prompt,
    tools=[send_email, get_weather],
    middleware=[middleware],
)
```

---

## How the middleware works

`PIIAnonymizationMiddleware` intercepts each agent turn at three points:

### `abefore_model` before the LLM

```mermaid
flowchart LR
    classDef user fill:#A5D6A7,stroke:#2E7D32,color:#000
    classDef mw fill:#BBDEFB,stroke:#1565C0,color:#000
    classDef llm fill:#FFF9C4,stroke:#F9A825,color:#000

    U["`**User**
    _'Send an email to Patrick in Paris'_`"]:::user
    M["`**Middleware**
    _NER detection via_
    _pipeline.anonymize()_`"]:::mw
    L["`**LLM sees**
    _'Send an email to <<PERSON_1>>_
    _in <<LOCATION_1>>'_`"]:::llm

    U --> M --> L
```

### `awrap_tool_call` around tools

```mermaid
flowchart TB
    classDef tool fill:#A5D6A7,stroke:#2E7D32,color:#000
    classDef mw fill:#BBDEFB,stroke:#1565C0,color:#000
    classDef llm fill:#FFF9C4,stroke:#F9A825,color:#000

    L1["`**LLM calls**
    _send_email(to='<<PERSON_1>>', ...)_`"]:::llm
    M1["`**Middleware**
    _deanonymize args_`"]:::mw
    T1["`**Tool receives**
    _to='Patrick' (real value)_`"]:::tool
    T2["`**Tool returns**
    _'Email successfully sent to Patrick.'_`"]:::tool
    M2["`**Middleware**
    _reanonymize response_`"]:::mw
    L2["`**LLM sees**
    _'Email successfully sent to <<PERSON_1>>.'_`"]:::llm

    L1 --> M1 --> T1 --> T2 --> M2 --> L2
```

### `aafter_model` after the LLM

```mermaid
flowchart LR
    classDef user fill:#A5D6A7,stroke:#2E7D32,color:#000
    classDef mw fill:#BBDEFB,stroke:#1565C0,color:#000
    classDef llm fill:#FFF9C4,stroke:#F9A825,color:#000

    L["`**LLM replies**
    _'Done! Email sent to <<PERSON_1>>.'_`"]:::llm
    M["`**Middleware**
    _deanonymize all messages_`"]:::mw
    U["`**User sees**
    _'Done! Email sent to Patrick.'_`"]:::user

    L --> M --> U
```

---

## Using the agent

```python
import asyncio

async def main():
    response = await graph.ainvoke({
        "messages": [{"role": "user", "content": "Send an email to Patrick in Paris"}]
    })
    print(response["messages"][-1].content)
    # Done! Email sent to Patrick.

asyncio.run(main())
```

---

## With Langfuse (observability)

The full example includes Langfuse integration to trace LLM calls:

```python
from langfuse import get_client
from langfuse.langchain import CallbackHandler

langfuse = get_client()
langfuse_handler = CallbackHandler()

graph = create_agent(
    model="openai:gpt-5.4",
    system_prompt=system_prompt,
    tools=[send_email, get_weather],
    middleware=[middleware],
    callbacks=[langfuse_handler],  # (1)!
)
```

1. Langfuse callbacks are added to `create_agent`. All LLM interactions are traced with **anonymized** text (the tracing layer never sees personal data).

---

## Deployment with Aegra

The `examples/graph/` example is designed to be deployed with [Aegra](https://aegra.dev/) (a self-hosted LangSmith alternative).

`aegra.json` file:

```json
{
  "graph": "./src/graph/graph.py:graph",
  "http": "./src/graph/app.py:app",
  "ttl": {
    "interval_minutes": 60,
    "default_minutes": 20160
  }
}
```

```bash
# Start the development server (graph + FastAPI on port 8000)
uv run aegra dev

# Full stack with PostgreSQL
docker compose up --build
```

---

## Environment variables

Copy `.env.example` to `.env` and fill in:

```bash
# LLM
OPENAI_API_KEY=sk-...
# or
ANTHROPIC_API_KEY=sk-ant-...

# Aegra (required)
AEGRA_CONFIG=aegra.json

# Database
DATABASE_URL=postgresql://user:pass@localhost:5432/piighost

# Observability (optional)
LANGFUSE_PUBLIC_KEY=...
LANGFUSE_SECRET_KEY=...
```
