"""JSON Lines emitter, Rich pretty renderer, and exit-code taxonomy."""

from __future__ import annotations

import enum
import json
import sys
from typing import IO, Any

from rich.console import Console
from rich.table import Table


class ExitCode(enum.IntEnum):
    SUCCESS = 0
    BUG = 1
    USER_ERROR = 2
    ANONYMIZATION_FAILED = 3
    DAEMON_UNREACHABLE = 4
    PII_SAFETY_VIOLATION = 5


def emit_json_line(obj: Any, *, stream: IO[str] | None = None) -> None:
    """Write ``obj`` as a single JSON line to ``stream`` (default stdout)."""
    target = stream if stream is not None else sys.stdout
    target.write(json.dumps(obj, ensure_ascii=False) + "\n")


def emit_error_line(
    *,
    error: str,
    message: str,
    hint: str | None = None,
    exit_code: ExitCode,
    stream: IO[str] | None = None,
) -> None:
    """Write a structured error JSON line to ``stream`` (default stderr)."""
    target = stream if stream is not None else sys.stderr
    payload = {
        "error": error,
        "message": message,
        "hint": hint,
        "exit_code": int(exit_code),
    }
    target.write(json.dumps(payload, ensure_ascii=False) + "\n")


def pretty_anonymize(console: Console, result: dict[str, Any]) -> None:
    """Render an anonymization result as a Rich table plus the anonymized text."""
    table = Table(title=f"doc: {result['doc_id']}")
    table.add_column("token")
    table.add_column("label")
    table.add_column("count", justify="right")
    for ent in result.get("entities", []):
        table.add_row(ent["token"], ent["label"], str(ent["count"]))
    console.print(table)
    console.print()
    console.print(result["anonymized"])
