"""Tests for piighost.exceptions."""

import pytest

from piighost.exceptions import CacheMissError, DeanonymizationError, PIIGhostException


class TestPIIGhostException:
    def test_is_exception(self):
        assert issubclass(PIIGhostException, Exception)

    def test_raise_and_catch(self):
        with pytest.raises(PIIGhostException, match="boom"):
            raise PIIGhostException("boom")


class TestCacheMissError:
    def test_is_piighost_exception(self):
        assert issubclass(CacheMissError, PIIGhostException)

    def test_raise_and_catch_as_base(self):
        with pytest.raises(PIIGhostException):
            raise CacheMissError("missing")

    def test_message_preserved(self):
        try:
            raise CacheMissError("key not found")
        except CacheMissError as exc:
            assert str(exc) == "key not found"


class TestDeanonymizationError:
    def test_is_piighost_exception(self):
        assert issubclass(DeanonymizationError, PIIGhostException)

    def test_stores_partial_text(self):
        exc = DeanonymizationError("token missing", partial_text="Hello <<PERSON:1>>")
        assert exc.partial_text == "Hello <<PERSON:1>>"
        assert str(exc) == "token missing"

    def test_raise_and_access_partial(self):
        with pytest.raises(DeanonymizationError) as info:
            raise DeanonymizationError("fail", partial_text="partial")
        assert info.value.partial_text == "partial"

    def test_partial_text_required(self):
        with pytest.raises(TypeError):
            DeanonymizationError("only message")  # type: ignore[call-arg]
