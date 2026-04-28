"""LLM-backed guard rail.

A guard rail that re-validates anonymized text via a LangChain chat
model. Useful as a final defence-in-depth check after a regex / NER
pipeline, especially in domains where the LLM has more context
awareness than narrow detectors (medical, legal, notarial).

Internally reuses ``LLMDetector`` with a guard-specific system prompt
that tells the model to ignore placeholders of the form ``<<LABEL:N>>``
or ``<<LABEL:HEX>>`` so it focuses on residual clear-text PII only.
"""

from __future__ import annotations

import importlib.util

if importlib.util.find_spec("langchain_core") is None:
    raise ImportError(
        "You must install langchain-core to use LLMGuardRail, "
        "please install piighost[llm]"
    )

from langchain_core.language_models import BaseChatModel

from piighost.detector.llm import LLMDetector
from piighost.exceptions import PIIRemainingError

_DEFAULT_GUARD_PROMPT = (
    "You are auditing text that has already been anonymized. "
    "Your job is to find Personally Identifiable Information (PII) "
    "that is still present in clear form, despite the anonymization "
    "step.\n\n"
    "Extract clear-form entities matching these labels:\n"
    "{labels}\n\n"
    "Tokens of the form <<LABEL:NUMBER>> or <<LABEL:HEX>> (for example "
    "<<PERSON:1>>, <<LOCATION:a3f9>>) are placeholders, not PII; never "
    "flag them. Only flag entities that appear in the text in clear "
    "form. If no clear-form PII remains, return an empty list."
)


class LLMGuardRail:
    """Guard rail backed by a LangChain chat model.

    Wraps an :class:`LLMDetector` with a guard-specific prompt and
    raises :class:`PIIRemainingError` if the model identifies any
    residual clear-text PII in the anonymized text.

    Args:
        model: A LangChain chat model supporting
            ``with_structured_output``.
        labels: Entity types the LLM should flag as residual
            (e.g. ``["PERSON", "LOCATION", "EMAIL"]``).
        prompt: Optional custom system prompt template.  Must contain
            a ``{labels}`` placeholder that will be replaced by the
            comma-separated label list.  When ``None``, a guard prompt
            tuned to ignore ``<<LABEL:N>>`` placeholders is used.

    Example:
        >>> from langchain_openai import ChatOpenAI
        >>> from piighost.guard_llm import LLMGuardRail
        >>> guard = LLMGuardRail(
        ...     model=ChatOpenAI(model="gpt-4o-mini"),
        ...     labels=["PERSON", "LOCATION", "EMAIL"],
        ... )
    """

    _detector: LLMDetector

    def __init__(
        self,
        model: BaseChatModel,
        labels: list[str],
        prompt: str | None = None,
    ) -> None:
        self._detector = LLMDetector(
            model=model,
            labels=labels,
            prompt=prompt or _DEFAULT_GUARD_PROMPT,
        )

    async def check(self, anonymized_text: str) -> None:
        residual = await self._detector.detect(anonymized_text)
        if residual:
            raise PIIRemainingError(
                f"{len(residual)} residual detection(s) reported by LLM",
                detections=list(residual),
            )


__all__ = ["LLMGuardRail"]
