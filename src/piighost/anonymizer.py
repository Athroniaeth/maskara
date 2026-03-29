from typing import Protocol

from piighost.models import Entity, Span
from piighost.placeholder import AnyPlaceholderFactory, CounterPlaceholderFactory


class AnyAnonymizer(Protocol):
    """Protocol defining the interface for all anonymizers.

    Any class implementing this protocol must provide methods for both
    anonymization and deanonymization of text based on entities.
    """

    ph_factory: AnyPlaceholderFactory

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


class Anonymizer:
    """Orchestrates anonymization and deanonymization of text.

    Uses a ``PlaceholderFactory`` to generate replacement tokens for
    entities, then performs span-based replacement on the text.

    Args:
        ph_factory: The placeholder factory to use for token generation.

    Example:
        >>> from piighost.models import Detection, Entity, Span
        >>> from piighost.placeholder import CounterPlaceholderFactory
        >>> entity = Entity(detections=[
        ...     Detection(text="Patrick", label="PERSON", position=Span(0, 7), confidence=0.9),
        ... ])
        >>> anonymizer = Anonymizer(CounterPlaceholderFactory())
        >>> anonymizer.anonymize("Patrick est gentil", [entity])
        '<<PERSON_1>> est gentil'
    """

    ph_factory: AnyPlaceholderFactory

    def __init__(self, ph_factory: AnyPlaceholderFactory | None) -> None:
        self.ph_factory = ph_factory or CounterPlaceholderFactory()

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
        # Since tokens may have different lengths than originals,
        # we process left to right and track the cumulative offset.
        restorations.sort(key=lambda r: r[0])

        offset = 0
        result = anonymized_text

        for original_pos, token, original_text in restorations:
            # Find the token starting from where we expect it to be,
            # accounting for the cumulative offset from previous replacements.
            search_start = original_pos + offset
            token_pos = result.find(token, search_start)

            if token_pos == -1:
                continue

            result = (
                result[:token_pos] + original_text + result[token_pos + len(token) :]
            )
            # Update offset: original text may be longer or shorter than token.
            offset += len(original_text) - len(token)

        return result
