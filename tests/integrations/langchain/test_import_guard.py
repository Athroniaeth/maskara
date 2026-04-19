"""The subpackage raises ImportError when langchain is missing."""

import importlib
import sys

import pytest


def test_import_raises_when_langchain_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    # Simulate langchain not being installed.
    import importlib.util as util

    real_find = util.find_spec

    def fake_find(name: str, *args: object, **kwargs: object):
        if name == "langchain":
            return None
        return real_find(name, *args, **kwargs)

    monkeypatch.setattr(util, "find_spec", fake_find)
    sys.modules.pop("piighost.integrations.langchain", None)

    with pytest.raises(ImportError, match="piighost\\[langchain\\]"):
        importlib.import_module("piighost.integrations.langchain")


def test_import_succeeds_when_langchain_present() -> None:
    pytest.importorskip("langchain")
    sys.modules.pop("piighost.integrations.langchain", None)
    mod = __import__("piighost.integrations.langchain", fromlist=["*"])
    assert mod is not None
