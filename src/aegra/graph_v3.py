"""Agent graph wired with PII anonymization middleware for end-to-end testing."""


from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.tools import tool
from loguru import logger
from langfuse import get_client
from langfuse.langchain import CallbackHandler
from aegra.middleware import PIIAnonymizationMiddleware, PIIState

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


pii = PIIAnonymizationMiddleware(threshold=0.5)

system_prompt = """\
You are a helpful assistant. Some inputs may contain anonymized placeholders that replace real values for privacy reasons.

Rules:
1. Treat every placeholder as if it were the real value, never comment on its format, never say it is a token, never ask the user to reveal it.
2. Placeholders can be passed directly to tools — use them as-is as input arguments. This preserves the user's privacy while \
still allowing tools to operate.
3. If the user asks for a specific detail about a token (e.g. "what is the first letter?"), reply briefly: "I cannot answer that question as the data has been anonymized to protect your personal information." \
Another example is if the user asks "Dans quel pays ce trouve la ville de {city} ?", you can answer "Je suis désolé, mais je ne peux pas répondre à cette question car les données ont été anonymisées pour protéger vos informations personnelles."
"""

# Initialize Langfuse client
langfuse = get_client()

# Initialize Langfuse CallbackHandler for Langchain (tracing)
langfuse_handler = CallbackHandler()

graph = create_agent(
    model="openai:gpt-5",
    system_prompt=system_prompt,
    state_schema=PIIState,
    tools=[send_email, get_weather],
    middleware=[pii],
)
