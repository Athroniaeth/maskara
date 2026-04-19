"""Top-level presets module is the single source of truth."""

from piighost.presets import PRESET_GDPR, PRESET_LANGUAGE, PRESET_SENSITIVITY


def test_gdpr_preset_shape() -> None:
    assert "gdpr_category" in PRESET_GDPR
    schema = PRESET_GDPR["gdpr_category"]
    assert set(schema["labels"]) >= {
        "health",
        "financial",
        "biometric",
        "political",
        "children",
        "none",
    }
    assert schema["multi_label"] is True


def test_sensitivity_preset_shape() -> None:
    schema = PRESET_SENSITIVITY["sensitivity"]
    assert schema["labels"] == ["low", "medium", "high"]
    assert schema["multi_label"] is False


def test_language_preset_shape() -> None:
    schema = PRESET_LANGUAGE["language"]
    assert set(schema["labels"]) >= {"fr", "en", "de", "es", "it", "nl"}
    assert schema["multi_label"] is False


def test_haystack_presets_are_same_objects() -> None:
    """BC: the Haystack re-export must be the identical dict object."""
    from piighost.integrations.haystack.presets import (
        PRESET_GDPR as HS_GDPR,
    )

    assert HS_GDPR is PRESET_GDPR
