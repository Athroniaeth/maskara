"""Agent graph wired with PII anonymization middleware for end-to-end testing."""

from dotenv import load_dotenv
from gliner2 import GLiNER2
from langchain.agents import create_agent
from langchain_core.tools import tool
from langfuse import get_client
from langfuse.langchain import CallbackHandler
from loguru import logger

from maskara.anonymizer import Anonymizer, GlinerDetector
from maskara.middleware import PIIAnonymizationMiddleware
from maskara.pipeline import AnonymizationPipeline

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
extractor = GLiNER2.from_pretrained("fastino/gliner2-multi-v1")

detector = GlinerDetector(model=extractor, threshold=0.5, flat_ner=True)
anonymizer = Anonymizer(detector=detector)
pipeline = AnonymizationPipeline(
    anonymizer=anonymizer,
    labels=["PERSON", "LOCATION"],
)
middleware = PIIAnonymizationMiddleware(pipeline=pipeline)
graph = create_agent(
    model="openai:gpt-5-mini",
    system_prompt=system_prompt,
    tools=[send_email, get_weather],
    middleware=[middleware],
)
