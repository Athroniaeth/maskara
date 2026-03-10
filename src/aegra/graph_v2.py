import functools
from collections import defaultdict
from typing import Annotated, TypedDict, Sequence

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, AnyMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langchain_experimental.data_anonymizer import PresidioReversibleAnonymizer
from langfuse.langchain import CallbackHandler
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from loguru import logger
from presidio_anonymizer.entities import OperatorConfig
from pydantic import BaseModel, Field

load_dotenv()


# ─────────────────────────────────────────────
# State
# ─────────────────────────────────────────────


class AnonymizedState(BaseModel):
    """Graph state that persists the anonymizer mapping across turns.

    Attributes:
        messages: Conversation history with LangChain add_messages reducer.
        anon_mapping: Serialized deanonymizer mapping keyed by entity type.
            Persisted per thread by LangGraph's checkpointer so placeholders
            remain resolvable across hot-reloads and multi-turn conversations.
    """

    messages: Annotated[Sequence[AnyMessage], add_messages] = Field(
        default_factory=list
    )
    anon_mapping: dict = Field(default_factory=dict)
# ─────────────────────────────────────────────
# Anonymizer
# ─────────────────────────────────────────────

ANALYZED_FIELDS = [
    "PERSON",
    "PHONE_NUMBER",
    "EMAIL_ADDRESS",
    "ORGANIZATION",
    "LOCATION",
]

anonymizer = PresidioReversibleAnonymizer(
    analyzed_fields=ANALYZED_FIELDS,
    languages_config={
        "nlp_engine_name": "spacy",
        "models": [{"lang_code": "fr", "model_name": "fr_core_news_lg"}],
    },
    operators={
        field: OperatorConfig("replace", {"new_value": None})
        for field in ANALYZED_FIELDS
    },
)


# ─────────────────────────────────────────────
# Tool decorator
# ─────────────────────────────────────────────


def with_deanonymized_args(fn):
    """Decorator that deanonymizes tool inputs and re-anonymizes the output.

    Ensures that tools always operate on real data while the LLM only
    ever sees anonymized placeholders (e.g. <PERSON_1>, <EMAIL_ADDRESS_1>).

    Args:
        fn: The tool function to wrap.

    Returns:
        A wrapped function with transparent deanonymization.
    """

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        real_args = [anonymizer.deanonymize(str(a)) for a in args]
        real_kwargs = {k: anonymizer.deanonymize(str(v)) for k, v in kwargs.items()}
        result = fn(*real_args, **real_kwargs)
        return anonymizer.anonymize(str(result))

    return wrapper


# ─────────────────────────────────────────────
# Tools
# ─────────────────────────────────────────────


@tool
@with_deanonymized_args
def get_weather(city: str) -> str:
    """Get the current weather for a given city.

    Args:
        city: The name of the city (may be an anonymized placeholder).

    Returns:
        A string describing the current weather.
    """
    return f"The weather in {city} is always sunny!"


@tool
@with_deanonymized_args
def send_email(to: str, subject: str, body: str) -> str:
    """Send an email to a given address.

    Args:
        to: Recipient email address (may be an anonymized placeholder).
        subject: Subject line of the email.
        body: Body content of the email.

    Returns:
        A confirmation string.
    """
    logger.debug(f"\n[EMAIL SENT] To: {to} | Subject: {subject}\n{body}\n")
    return f"Email successfully sent to {to}."


# ─────────────────────────────────────────────
# Graph nodes
# ─────────────────────────────────────────────


def _extract_text(content: str | list) -> str:
    """Extract plain text from a message content field.

    LangChain message content can be either a plain string or a list of
    content blocks (multimodal format). This function normalises both forms
    to a single string so Presidio can process it.

    Args:
        content: Either a plain string or a list of content blocks such as
            ``[{"type": "text", "text": "..."}]``.

    Returns:
        The concatenated text extracted from the content.
    """
    if isinstance(content, str):
        return content
    return " ".join(
        block.get("text", "") for block in content if isinstance(block, dict)
    )


def anonymize_input(state: AnonymizedState) -> AnonymizedState:
    """Anonymize the last human message before it reaches the LLM.

    Restores the thread's placeholder mapping from state so that entities
    anonymized in previous turns keep their original placeholders (e.g.
    ``<LOCATION_1>`` stays ``<LOCATION_1>`` across turns). Replaces PII
    entities with stable placeholders so the model never processes raw
    sensitive data.

    Args:
        state: Current graph state containing the message history and the
            persisted anonymizer mapping for this thread.

    Returns:
        Updated state with the last human message anonymized and the
        mapping saved for subsequent turns.
    """
    anonymizer._deanonymizer_mapping.mapping = defaultdict(
        dict, state.anon_mapping
    )
    messages = list(state.messages)
    last = messages[-1]
    if isinstance(last, HumanMessage):
        text = _extract_text(last.content)
        anonymized = anonymizer.anonymize(text, language="fr")
        logger.debug(f"[ANONYMIZED INPUT]  {anonymized}")
        messages[-1] = HumanMessage(content=anonymized, id=last.id)
    return {"messages": messages, "anon_mapping": anonymizer.deanonymizer_mapping}


def deanonymize_output(state: AnonymizedState) -> AnonymizedState:
    """Restore real values in the AI response and the user's message.

    Deanonymizes the last AI message so the final response is human-readable,
    and also restores the last human message to its original form so that the
    thread history stored by LangGraph's checkpointer never exposes placeholders
    to the end user (e.g. when reloading a conversation in the UI).

    Args:
        state: Current graph state containing the message history and the
            persisted anonymizer mapping for this thread.

    Returns:
        Updated state with both the AI response and the last human message
        deanonymized, and the mapping saved for subsequent turns.
    """
    messages = list(state.messages )
    result: list[BaseMessage] = []

    last = messages[-1]
    if isinstance(last, AIMessage):
        deanonymized = anonymizer.deanonymize(_extract_text(last.content))
        logger.debug(f"[DEANONYMIZED OUTPUT] {deanonymized}")
        result.append(AIMessage(content=deanonymized, id=last.id))

    for msg in reversed(messages[:-1]):
        if isinstance(msg, HumanMessage):
            original = anonymizer.deanonymize(_extract_text(msg.content))
            result.append(HumanMessage(content=original, id=msg.id))
            break

    return {"messages": result, "anon_mapping": anonymizer.deanonymizer_mapping}


# ─────────────────────────────────────────────
# LLM & agent
# ─────────────────────────────────────────────

SYSTEM_PROMPT = """You are a helpful assistant with access to weather and email tools.

IMPORTANT: User inputs may contain anonymized placeholders like <PERSON_1>, <EMAIL_ADDRESS_1>, <LOCATION_1>, etc.
Pass these placeholders as-is to the tools — they will automatically resolve to the real values internally.
Never try to guess or replace the placeholders yourself.

The user is not aware that words in their message may be replaced by placeholders. For example, 
they ask you which city is next to Lyon, but you will see LOCATION_1, so you will not be able 
to provide them with the answer. Explain to them that their message is anonymized with regard 
to personal data such as city names, so you cannot provide them with the answer."""

llm = init_chat_model(model="gpt-5-nano")

agent = create_agent(
    model=llm,
    tools=[get_weather, send_email],
    system_prompt=SYSTEM_PROMPT,
)

langfuse_handler = CallbackHandler()
config = RunnableConfig(callbacks=[langfuse_handler])

# ─────────────────────────────────────────────
# Graph assembly
# ─────────────────────────────────────────────

builder = StateGraph(AnonymizedState)  # pyrefly: ignore[bad-specialization]
builder.add_node(
    "anonymize_input", anonymize_input
)  # pyrefly: ignore[no-matching-overload]
builder.add_node("agent", agent)  # pyrefly: ignore[no-matching-overload]
builder.add_node(
    "deanonymize_output", deanonymize_output
)  # pyrefly: ignore[no-matching-overload]

builder.set_entry_point("anonymize_input")
builder.add_edge("anonymize_input", "agent")
builder.add_edge("agent", END)
# builder.add_edge("agent", "deanonymize_output")
# builder.add_edge("deanonymize_output", END)

graph = builder.compile(name="aegra_v2").with_config(config)

# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

if __name__ == "__main__":
    questions = [
        "What's the weather like in Paris?",
        "Send an email to jean.dupont@acme.com to tell him it's sunny in London.",
        "What's the weather in Tokyo? Send the result to marie.martin@startup.io",
    ]

    for question in questions:
        logger.debug(f"\n{'=' * 60}")
        logger.debug(f"[USER]  {question}")
        response = graph.invoke({"messages": [("human", question)]}, config=config)
        logger.debug(f"[AGENT] {response['messages'][-1].content}")
