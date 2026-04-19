"""Tests for the ``lancedb_meta_fields`` helper (no lancedb required)."""

import pyarrow as pa

from piighost.integrations.haystack.lancedb import lancedb_meta_fields
from piighost.integrations.haystack.presets import PRESET_SENSITIVITY


class TestWithoutSchemas:
    """Without classification schemas, all fields are plain strings."""

    def test_all_string_fields(self) -> None:
        fields = dict(lancedb_meta_fields())
        assert fields["piighost_mapping"] == pa.string()
        assert fields["piighost_profile"] == pa.string()
        assert fields["labels"] == pa.string()
        assert fields["piighost_error"] == pa.string()


class TestWithSchemas:
    """Schemas make ``labels`` a struct for filter-friendly indexing."""

    def test_labels_is_struct_with_schema_keys(self) -> None:
        fields = dict(lancedb_meta_fields(schemas=PRESET_SENSITIVITY))
        labels_type = fields["labels"]
        assert isinstance(labels_type, pa.StructType)
        names = {labels_type.field(i).name for i in range(labels_type.num_fields)}
        assert names == {"sensitivity"}
        assert labels_type.field("sensitivity").type == pa.list_(pa.string())

    def test_other_fields_still_string(self) -> None:
        fields = dict(lancedb_meta_fields(schemas=PRESET_SENSITIVITY))
        assert fields["piighost_mapping"] == pa.string()
        assert fields["piighost_profile"] == pa.string()

    def test_multiple_schemas_combine(self) -> None:
        from piighost.integrations.haystack.presets import PRESET_LANGUAGE

        fields = dict(
            lancedb_meta_fields(schemas={**PRESET_SENSITIVITY, **PRESET_LANGUAGE})
        )
        labels_type = fields["labels"]
        names = {labels_type.field(i).name for i in range(labels_type.num_fields)}
        assert names == {"sensitivity", "language"}
