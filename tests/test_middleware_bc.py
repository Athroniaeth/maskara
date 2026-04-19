"""The legacy import path still resolves."""

import pytest

pytest.importorskip("langchain")


def test_legacy_path_still_exports_middleware() -> None:
    from piighost.middleware import PIIAnonymizationMiddleware
    from piighost.integrations.langchain.middleware import (
        PIIAnonymizationMiddleware as New,
    )

    assert PIIAnonymizationMiddleware is New
