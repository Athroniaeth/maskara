"""Agent graph wired with PII anonymization middleware for end-to-end testing."""

from typing import Callable, Awaitable

from dotenv import load_dotenv
from gliner2 import GLiNER2
from langchain.agents import create_agent
from langchain.agents.middleware import (
    AgentMiddleware,
    ModelRequest,
    ExtendedModelResponse,
)
from langchain.agents.middleware.types import ModelResponse, ResponseT
from langchain_core.messages import AIMessage, AnyMessage
from langchain_core.tools import tool
from langgraph.config import get_config
from langgraph.typing import ContextT
from loguru import logger
from langfuse import get_client
from langfuse.langchain import CallbackHandler

from maskara.anonymizer import Anonymizer

load_dotenv()


@tool
def send_email(to: str, subject: str, body: str) -> str:
    """Send an email to a given address.

    Args:
        to: Recipient email address.
        subject: Email subject line.
        body: Email body text.

    Returns:
        Confirmation string.
    """
    logger.info("\n[EMAIL SENT] To: {} | Subject: {}\n{}\n", to, subject, body)
    return f"Email successfully sent to {to}."


@tool
def get_weather(country_or_city: str) -> str:
    """Get the current weather for a given country or city.

    Args:
        country_or_city: Name of the location to query.

    Returns:
        A weather summary string.
    """
    return f"The weather in {country_or_city} is 22°C and sunny."


class MockAnonymizer:
    def deanonymize_messages(self, messages: list[AnyMessage]) -> list[AnyMessage]:
        for message in messages:
            assert isinstance(message.content, str), (
                "This simple anonymizer only works for string content."
            )
            if "{name}" in message.content:
                message.content = message.content.replace("{name}", "Pierre")
            if "{city}" in message.content:
                message.content = message.content.replace("{city}", "Lyon")
        return messages

    def anonymize_messages(self, messages: list[AnyMessage]) -> list[AnyMessage]:
        new_messages = []
        for message in messages:
            assert isinstance(message.content, str), (
                "This simple anonymizer only works for string content."
            )
            message.content = message.content.replace("Pierre", "{name}")
            message.content = message.content.replace("Lyon", "{city}")
            new_messages.append(message)
        return new_messages


class CustomMiddleware(AgentMiddleware):
    def __init__(self, extractor: GLiNER2):
        super().__init__()
        self.anonymizer = Anonymizer(extractor)

    async def awrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[
            [ModelRequest[ContextT]], Awaitable[ModelResponse[ResponseT]]
        ],
    ) -> ModelResponse[ResponseT] | AIMessage | ExtendedModelResponse[ResponseT]:
        # Cache uniquement la réponse du modèle sur l'interface et au rechargement du thread
        config = get_config()
        thread_id = config["configurable"]["thread_id"]
        print(f"Thread ID: {thread_id}")

        print(f"Model request: {request.messages}")
        request.messages, _placeholders = self.anonymizer.anonymize_messages(
            request.messages, thread_id=thread_id
        )
        print(f"Model request after anonymization: {request.messages}\n")

        response = await handler(request)

        ai_msg = response.result[0]
        assert isinstance(ai_msg, AIMessage), (
            "This middleware only supports AIMessage responses."
        )

        print(f"Model request before deanonymization: {request.messages}\n")
        print(f"Model response before deanonymization: {ai_msg.content}")

        ai_msg = self.anonymizer.deanonymize_messages([ai_msg], thread_id=thread_id)[0]
        request.messages = self.anonymizer.deanonymize_messages(request.messages, thread_id=thread_id)

        print(f"Model request after deanonymization: {request.messages}")
        print(f"Model response after deanonymization: {ai_msg.content}")
        return ModelResponse(
            result=[ai_msg],
            structured_response=response.structured_response,
        )


system_prompt = """\
You are a helpful assistant. Some inputs may contain anonymized placeholders that replace real values for privacy reasons.

Rules:
1. Treat every placeholder as if it were the real value, never comment on its format, never say it is a token, never ask the user to reveal it.
2. Placeholders can be passed directly to tools use them as-is as input arguments. This preserves the user's privacy while \
still allowing tools to operate.
3. If the user asks for a specific detail about a token (e.g. "what is the first letter?"), reply briefly: "I cannot answer that question as the data has been anonymized to protect your personal information." \
Another example is if the user asks "Dans quel pays ce trouve la ville de {city} ?", you can answer "Je suis désolé, mais je ne peux pas répondre à cette question car les données ont été anonymisées pour protéger vos informations personnelles."
"""

# Initialize Langfuse client
langfuse = get_client()

# Initialize Langfuse CallbackHandler for Langchain (tracing)
langfuse_handler = CallbackHandler()
extractor = GLiNER2.from_pretrained("fastino/gliner2-base-v1")
middleware = CustomMiddleware(extractor=extractor)

graph = create_agent(
    model="openai:gpt-5-nano",
    system_prompt=system_prompt,
    tools=[send_email, get_weather],
    middleware=[middleware],
)
