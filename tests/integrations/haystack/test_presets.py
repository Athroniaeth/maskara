"""Tests for the GDPR / sensitivity / language presets."""

from piighost.integrations.haystack.presets import (
    PRESET_GDPR,
    PRESET_LANGUAGE,
    PRESET_SENSITIVITY,
)


class TestPresets:
    """Presets are well-formed ClassificationSchema dicts."""

    def test_gdpr_preset_has_expected_axes(self) -> None:
        assert "gdpr_category" in PRESET_GDPR
        schema = PRESET_GDPR["gdpr_category"]
        assert "health" in schema["labels"]
        assert "none" in schema["labels"]
        assert schema["multi_label"] is True

    def test_sensitivity_preset_is_single_label(self) -> None:
        schema = PRESET_SENSITIVITY["sensitivity"]
        assert schema["labels"] == ["low", "medium", "high"]
        assert schema["multi_label"] is False

    def test_language_preset_has_common_codes(self) -> None:
        schema = PRESET_LANGUAGE["language"]
        for code in ("fr", "en", "de"):
            assert code in schema["labels"]
