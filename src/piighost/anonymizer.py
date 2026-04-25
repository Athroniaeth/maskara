from typing import Generic, Protocol

from typing_extensions import TypeVar

from piighost.exceptions import DeanonymizationError
from piighost.models import Entity, Span
from piighost.placeholder import AnyPlaceholderFactory, LabelCounterPlaceholderFactory
from piighost.placeholder_tags import PlaceholderPreservation

PreservationT = TypeVar(
    "PreservationT",
    bound=PlaceholderPreservation,
    default=PlaceholderPreservation,
)
"""Tag carried by the factory the anonymiser wraps."""


class AnyAnonymizer(Protocol[PreservationT]):
    """Protocol defining the interface for all anonymizers.

    Any class implementing this protocol must provide methods for both
    anonymization and deanonymization of text based on entities.

    The generic parameter propagates the preservation tag of the
    underlying :class:`AnyPlaceholderFactory` so downstream consumers
    (pipeline, middleware) can constrain what they accept.
    """

    ph_factory: AnyPlaceholderFactory[PreservationT]

    def anonymize(self, text: str, entities: list[Entity]) -> str:
        """Replace entity detections in the text with tokens.

        Args:
            text: The original text to anonymize.
            entities: The entities whose detections should be replaced.

        Returns:
            The anonymized text with all detections replaced by tokens.
        """
        ...

    def deanonymize(self, anonymized_text: str, entities: list[Entity]) -> str:
        """Restore the original text from an anonymized version.

        Args:
            anonymized_text: The text to deanonymize.
            entities: The same entities used during anonymization,
                carrying the original detection texts and positions.

        Returns:
            The restored original text.
        """
        ...


class Anonymizer(Generic[PreservationT]):
    """Orchestrates anonymization and deanonymization of text.

    Uses a ``PlaceholderFactory`` to generate replacement tokens for
    entities, then performs span-based replacement on the text.

    Args:
        ph_factory: The placeholder factory to use for token generation.

    Example:
        >>> from piighost.models import Detection, Entity, Span
        >>> from piighost.placeholder import LabelCounterPlaceholderFactory
        >>> entity = Entity(detections=[
        ...     Detection(text="Patrick", label="PERSON", position=Span(0, 7), confidence=0.9),
        ... ])
        >>> anonymizer = Anonymizer(LabelCounterPlaceholderFactory())
        >>> anonymizer.anonymize("Patrick est gentil", [entity])
        '<<PERSON:1>> est gentil'
    """

    ph_factory: AnyPlaceholderFactory[PreservationT]

    def __init__(
        self,
        ph_factory: AnyPlaceholderFactory[PreservationT] | None = None,
    ) -> None:
        self.ph_factory = ph_factory or LabelCounterPlaceholderFactory()  # type: ignore[assignment]

    def anonymize(self, text: str, entities: list[Entity]) -> str:
        """Replace each detection in the text with its entity's token.

        Replacements are applied from right to left so that earlier
        span positions remain valid after each replacement.

        Args:
            text: The original text to anonymize.
            entities: The entities whose detections should be replaced.

        Returns:
            The anonymized text with all detections replaced by tokens.
        """
        # Build the list of (start, end, token) replacements.
        replacements: list[tuple[Span, str]] = []

        # Ask the factory to create all tokens at once.
        tokens = self.ph_factory.create(entities)

        for entity, token in tokens.items():
            for detection in entity.detections:
                replacement = (detection.position, token)
                replacements.append(replacement)

        # Sort by start position descending (right to left).
        # This way, replacing a span doesn't shift the positions
        # of spans that come before it in the text.
        replacements.sort(key=lambda r: r[0].start_pos, reverse=True)

        result = text
        for pos, token in replacements:
            result = result[: pos.start_pos] + token + result[pos.end_pos :]

        return result

    def deanonymize(self, anonymized_text: str, entities: list[Entity]) -> str:
        """Restore the original text from an anonymized version.

        For each entity, finds the token that was used to anonymize it,
        then replaces each occurrence of that token with the original
        detection text, in order of position.

        Args:
            anonymized_text: The text to deanonymize.
            entities: The same entities used during anonymization,
                carrying the original detection texts and positions.

        Returns:
            The restored original text.
        """
        # Recreate the same tokens for each entity.
        tokens = self.ph_factory.create(entities)

        # Build a list of (original_position, token, original_text)
        # so we can replace tokens in the correct order.
        # We use the original position to know WHICH detection each
        # token occurrence corresponds to (important when the same entity
        # has detections with different spellings like "Patrick" vs "patric").
        restorations: list[tuple[int, str, str]] = []

        for entity, token in tokens.items():
            for detection in entity.detections:
                restorations.append(
                    (
                        detection.position.start_pos,
                        token,
                        detection.text,
                    )
                )

        # Sort by original position ascending.
        # We process left to right, searching for each token from
        # where the previous replacement ended.
        restorations.sort(key=lambda r: r[0])

        result = anonymized_text
        search_from = 0

        for original_pos, token, original_text in restorations:
            token_pos = result.find(token, search_from)

            if token_pos == -1:
                raise DeanonymizationError(
                    f"Token {token!r} not found in text during deanonymization",
                    partial_text=result,
                )

            result = (
                result[:token_pos] + original_text + result[token_pos + len(token) :]
            )
            search_from = token_pos + len(original_text)

        return result
