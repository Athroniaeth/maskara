"""Backwards-compatible re-export. New code should import from ``piighost.presets``."""

from piighost.presets import PRESET_GDPR, PRESET_LANGUAGE, PRESET_SENSITIVITY

__all__ = ["PRESET_GDPR", "PRESET_LANGUAGE", "PRESET_SENSITIVITY"]
