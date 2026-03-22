# PIIGhost — PII Anonymization Example

This example demonstrates PIIGhost's PII anonymization middleware integrated into a LangGraph agent. All sensitive entities (names, locations, etc.) are transparently detected and anonymized before reaching the LLM, then deanonymized in the response shown to the user.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) — Python package manager
- [pnpm](https://pnpm.io/) — Node.js package manager (for the frontend)
- [Docker](https://www.docker.com/) — for PostgreSQL (or full-stack deployment)

## Quick Start

### 1. Backend

```bash
# Copy and fill in your environment variables (at minimum: OPENAI_API_KEY)
cp .env.example .env

# Start PostgreSQL
docker compose up postgres -d

# Install dependencies and start the dev server (http://localhost:8000)
uv sync
uv run aegra dev
```

### 2. Frontend

```bash
cd front
pnpm install
pnpm dev
```

Open [http://localhost:3000](http://localhost:3000), then fill in the connection form:

| Field | Value |
|---|---|
| Deployment URL | `http://localhost:8000` |
| Assistant / Graph ID | `agent` |

## Full Stack (Docker)

To run both PostgreSQL and the API in containers:

```bash
docker compose up --build
```

The API will be available at `http://localhost:8000`.

## Available Tools

The agent exposes two tools:

- `get_weather(country_or_city)` — returns current weather for a location
- `send_email(to, subject, body)` — simulates sending an email (logs to stdout)

## Example Conversation

The following conversation shows PII anonymization in action. The user's name and location are replaced with placeholders (`<<PERSON_1>>`, `<<LOCATION_1>>`) before the LLM processes them.

---

**User:** Hello, my name is Patrick, I live in France.

**Agent:** Hello! Nice to meet you. How can I help you today? For example: weather, local recommendations, translation, documents, or anything else?

---

**User:** What letter does my first name start with?

**Agent:** I'm sorry, but I can't answer that question — personal data has been anonymized to protect your information.

---

**User:** Can you give me the weather where I live?

**Agent:** *(calls `get_weather("France")`)*

> The weather in France is 22°C and sunny.

It's 22°C and sunny where you live. Would you like a forecast for the coming days?

---

Notice that even though the agent sees `<<PERSON_1>>` and `<<LOCATION_1>>` internally, it still correctly routes the `get_weather` tool call to the right location — and the final response is deanonymized before being displayed.
