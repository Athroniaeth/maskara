"""Helper to build LanceDB-Haystack metadata schema fields.

LanceDB-Haystack enforces its metadata schema with PyArrow at store
creation time — unknown meta fields are rejected.  Users must declare
piighost's fields up front; this module provides a helper that does so
and, when classification schemas are provided, generates a struct type
for the ``labels`` meta field so it can be filtered on.
"""

import pyarrow as pa

from piighost.classifier.base import ClassificationSchema


def lancedb_meta_fields(
    schemas: dict[str, ClassificationSchema] | None = None,
) -> tuple[tuple[str, pa.DataType], ...]:
    """Return ``(name, pa.DataType)`` pairs to spread into a LanceDB schema.

    Example:
        >>> import pyarrow as pa
        >>> from piighost.integrations.haystack.lancedb import lancedb_meta_fields
        >>> from piighost.integrations.haystack.presets import PRESET_SENSITIVITY
        >>> metadata_schema = pa.struct([
        ...     ("title", pa.string()),
        ...     *lancedb_meta_fields(schemas=PRESET_SENSITIVITY),
        ... ])

    Args:
        schemas: Optional classification schemas used by
            ``PIIGhostDocumentClassifier``.  When provided, the returned
            ``labels`` field is a ``pa.struct`` with one ``list<string>``
            subfield per axis so LanceDB can filter on them.  When
            ``None``, ``labels`` is a plain ``pa.string()`` (JSON-encoded,
            not filterable).

    Returns:
        A tuple of ``(field_name, pa.DataType)`` pairs.
    """
    if schemas:
        labels_type: pa.DataType = pa.struct(
            [(name, pa.list_(pa.string())) for name in schemas]
        )
    else:
        labels_type = pa.string()

    return (
        ("piighost_mapping", pa.string()),
        ("piighost_profile", pa.string()),
        ("piighost_error", pa.string()),
        ("labels", labels_type),
    )
