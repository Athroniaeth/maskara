import io
import json

from piighost.cli.output import (
    ExitCode,
    emit_error_line,
    emit_json_line,
)


def test_emit_json_line_writes_jsonl() -> None:
    buf = io.StringIO()
    emit_json_line({"a": 1, "b": "x"}, stream=buf)
    emit_json_line({"a": 2}, stream=buf)
    lines = buf.getvalue().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0]) == {"a": 1, "b": "x"}
    assert json.loads(lines[1]) == {"a": 2}


def test_emit_error_line_has_structure() -> None:
    buf = io.StringIO()
    emit_error_line(
        error="VaultNotFound",
        message="nope",
        hint="run init",
        exit_code=ExitCode.USER_ERROR,
        stream=buf,
    )
    parsed = json.loads(buf.getvalue())
    assert parsed["error"] == "VaultNotFound"
    assert parsed["exit_code"] == 2


def test_exit_code_taxonomy() -> None:
    assert int(ExitCode.SUCCESS) == 0
    assert int(ExitCode.BUG) == 1
    assert int(ExitCode.USER_ERROR) == 2
    assert int(ExitCode.ANONYMIZATION_FAILED) == 3
    assert int(ExitCode.DAEMON_UNREACHABLE) == 4
    assert int(ExitCode.PII_SAFETY_VIOLATION) == 5
