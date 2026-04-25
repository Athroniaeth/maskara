# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "piighost[cache]",
#   "gliner2>=1.2.0",
#   "instructor>=1.6.0",
#   "openai>=1.50.0",
#   "pydantic>=2.0",
#   "python-dotenv>=1.0.0",
# ]
#
# [tool.uv.sources]
# piighost = { path = "../..", editable = true }
# ///
"""Structured extraction through a LiteLLM proxy, with PII kept out of the LLM.

Flow:
    1. Anonymize the input text with PIIGhost.
    2. Send the anonymized text to the LLM via ``instructor`` + a Pydantic
       schema. The LLM echoes placeholders into the structured fields.
    3. Deanonymize the Pydantic result by round-tripping its JSON dump
       through the entities collected at step 1.

Run with:
    uv run examples/llm/instructor_structured.py
"""

import asyncio
import os
from pathlib import Path

import instructor
from dotenv import load_dotenv
from gliner2 import GLiNER2
from openai import AsyncOpenAI
from pydantic import BaseModel

from piighost.anonymizer import Anonymizer
from piighost.detector.gliner2 import Gliner2Detector
from piighost.pipeline.base import AnonymizationPipeline
from piighost.placeholder import LabelCounterPlaceholderFactory


class Profile(BaseModel):
    name: str
    city: str
    short_bio: str


SYSTEM_PROMPT = (
    "You extract structured profiles from free-form text.\n"
    "\n"
    "The input has been anonymized: real names and locations are replaced "
    "with placeholders of the form <<LABEL_N>>, e.g. <<PERSON_1>> or "
    "<<LOCATION_1>>. Treat each placeholder as the real value it replaces, "
    "but you MUST copy it verbatim (with the surrounding double angle "
    "brackets and the trailing number) into the corresponding field of the "
    "output JSON. Never strip the brackets, never invent a name or city, "
    "never describe the placeholder format."
)

USER_PROMPT = (
    "Extract a profile from this: "
    "Patrick is a software engineer from Paris who loves hiking."
)


def build_pipeline() -> AnonymizationPipeline:
    model = GLiNER2.from_pretrained("fastino/gliner2-multi-v1")
    detector = Gliner2Detector(
        model=model,
        labels=["PERSON", "LOCATION"],
        threshold=0.5,
        flat_ner=True,
    )
    return AnonymizationPipeline(
        detector=detector,
        anonymizer=Anonymizer(LabelCounterPlaceholderFactory()),
    )


def deanonymize(pipeline: AnonymizationPipeline, text: str, entities: list) -> str:
    """Replace every placeholder token in *text* with its original value."""
    tokens = pipeline.ph_factory.create(entities)
    for entity, token in tokens.items():
        text = text.replace(token, entity.detections[0].text)
    return text


async def main() -> None:
    load_dotenv(Path(__file__).with_name(".env"))

    pipeline = build_pipeline()
    anonymized_prompt, entities = await pipeline.anonymize(USER_PROMPT)
    print(f"[anonymized prompt] {anonymized_prompt}\n")

    # LiteLLM proxy is OpenAI-compatible, so we drive it through the OpenAI
    # SDK wrapped by instructor.
    client = instructor.from_openai(
        AsyncOpenAI(
            base_url=os.getenv("LITELLM_BASE_URL"),
            api_key=os.getenv("LITELLM_API_KEY"),
        )
    )

    profile = await client.chat.completions.create(
        model=os.getenv("LITELLM_MODEL", "gpt-5.4-mini"),
        response_model=Profile,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": anonymized_prompt},
        ],
    )

    print(f"[anonymized result]\n{profile.model_dump_json(indent=2)}\n")
    """
    [anonymized result]
    {
      "name": "<<PERSON_1>>",
      "city": "<<LOCATION_1>>",
      "short_bio": "Software engineer who loves hiking."
    }
    """

    deanonymized_json = deanonymize(pipeline, profile.model_dump_json(), entities)
    deanonymized_profile = Profile.model_validate_json(deanonymized_json)
    print(f"[deanonymized result]\n{deanonymized_profile.model_dump_json(indent=2)}")
    """
    
    [deanonymized result]
    {
      "name": "Patrick",
      "city": "Paris",
      "short_bio": "Software engineer who loves hiking."
    }
    """


if __name__ == "__main__":
    asyncio.run(main())
