"""How a CLI command shows its result: Rich for people, text for pipes, JSON on request.

A command returns its result and one handler on the root app (`RESULT_ACTION`, wired
through cyclopts' `result_action`) shows it, so a command cannot forget to, and tests
can call a command and assert on what it returns. A `Report` adds a title, the text for
an empty list, and an exit status. The format is chosen once, by the CLI's global
`--format` / `--json` flag. `auto` (the
default) shows Rich on a terminal and plain text when stdout is piped, redirected or
read by a dumb terminal; JSON is only ever shown when asked for.

Results go to stdout. Logs, progress and errors go to stderr or the logger.
"""

import dataclasses
import json
import os
import sys
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from enum import Enum, StrEnum
from pathlib import PurePath
from typing import Any
from uuid import UUID

from rich.console import Console
from rich.table import Table
from rich.text import Text

# A command's result: anything made of dataclasses, mappings, sequences and scalars.
type Result = object


class OutputFormat(StrEnum):
    """How results are shown."""

    AUTO = "auto"
    RICH = "rich"
    TEXT = "text"
    JSON = "json"


@dataclasses.dataclass(frozen=True, kw_only=True)
class Report:
    """A result with how to show it and the exit status the command finishes with.

    A command may return a bare dict, list or dataclass instead when it needs none of
    that. The exit status follows cyclopts' `__cyclopts_returncode__` protocol.
    """

    value: Result
    title: str | None = None
    empty: str = "Nothing to show."
    exit_code: int = 0

    def __cyclopts_returncode__(self) -> int:
        """Tell cyclopts which status to exit with."""
        return self.exit_code


_format = OutputFormat.AUTO


def set_format(output_format: OutputFormat) -> None:
    """Choose the format for the rest of this process."""
    global _format
    _format = output_format


def resolved_format() -> OutputFormat:
    """The format in effect: `auto` is Rich on a capable terminal, else plain text."""
    if _format is not OutputFormat.AUTO:
        return _format
    capable = sys.stdout.isatty() and os.environ.get("TERM") != "dumb"
    return OutputFormat.RICH if capable else OutputFormat.TEXT


def to_data(value: object) -> Any:  # noqa: ANN401 - JSON-shaped data has no static type
    """Turn a result into plain JSON-ready data: dicts, lists and scalars."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            f.name: to_data(getattr(value, f.name)) for f in dataclasses.fields(value)
        }
    if isinstance(value, Mapping):
        return {str(key): to_data(item) for key, item in value.items()}
    if isinstance(value, Enum):
        return to_data(value.value)
    if isinstance(value, (set, frozenset)):
        return sorted((to_data(item) for item in value), key=str)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [to_data(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (UUID, PurePath)):
        return str(value)
    return value


def format_bytes(count: int) -> str:
    """1536 becomes "1.5 KiB"."""
    size = float(count)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if abs(size) < 1024 or unit == "GiB":
            return f"{int(size)} B" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{count} B"  # pragma: no cover - the loop always returns


def _label(key: str) -> str:
    return key.replace("_", " ").capitalize()


def _is_size(key: str) -> bool:
    return key == "size" or key.endswith(("_bytes", "_size"))


def _is_time(key: str) -> bool:
    return key.endswith(("_at", "_until")) or key in {"cutoff", "created", "started"}


def _when(value: str) -> str:
    """Write an ISO time as `2026-10-28 15:00 UTC`; leave anything else alone."""
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return value
    return moment.strftime("%Y-%m-%d %H:%M %Z").strip()


def _cell(key: str, value: object) -> Text:
    if isinstance(value, str) and _is_time(key):
        return Text(_when(value))
    if isinstance(value, bool):
        return Text("yes" if value else "no")
    if value is None:
        return Text("—", style="dim")
    if isinstance(value, int) and _is_size(key):
        return Text(format_bytes(value))
    if isinstance(value, list):
        return Text(", ".join(str(item) for item in value) if value else "—")
    if isinstance(value, dict):
        return Text(", ".join(f"{_label(k)}: {v}" for k, v in value.items()) or "—")
    return Text(str(value))


def _field_table(data: Mapping[str, Any], title: str | None) -> Table:
    table = Table("Field", "Value", title=title, title_justify="left")
    for key, value in data.items():
        table.add_row(Text(_label(key)), _cell(key, value))
    return table


def _row_table(rows: Sequence[Mapping[str, Any]], title: str | None) -> Table:
    columns = list(dict.fromkeys(key for row in rows for key in row))
    table = Table(*(_label(c) for c in columns), title=title, title_justify="left")
    for row in rows:
        table.add_row(*(_cell(c, row.get(c)) for c in columns))
    return table


def render_rich(
    console: Console,
    value: Result,
    *,
    title: str | None = None,
    empty: str,
    failed: bool = False,
) -> None:
    """Draw a result: a message with its details, a field table, or a row table."""
    data = to_data(value)
    if isinstance(data, Mapping):
        if "message" in data:
            mark, style = ("✗", "red") if failed else ("✓", "green")
            console.print(Text(f"{mark} {data['message']}", style=style))
            details = {k: v for k, v in data.items() if k != "message"}
            if details:
                console.print(_field_table(details, title))
        else:
            console.print(_field_table(data, title))
    elif isinstance(data, list) and not data:
        console.print(Text(empty, style="dim"))
    elif isinstance(data, list) and all(isinstance(row, Mapping) for row in data):
        console.print(_row_table(data, title))
    elif isinstance(data, list):
        for item in data:
            console.print(Text(f"• {item}"))
    else:
        console.print(Text(str(data)))


def _plain(key: str, value: object) -> str:
    """A value as plain text: yes/no, a dash for nothing, sizes as people write them."""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if value is None:
        return "-"
    if isinstance(value, int) and _is_size(key):
        return format_bytes(value)
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) if value else "-"
    if isinstance(value, dict):
        return ", ".join(f"{k}={v}" for k, v in value.items()) or "-"
    return str(value)


def render_text(value: Result, *, title: str | None = None, empty: str) -> str:
    """The result as plain lines, easy to read in a log and to grep.

    A mapping is `key: value` lines (after its message, if it has one), a list of
    records is a header and aligned columns, and a list of plain values is one per line.
    """
    data = to_data(value)
    if isinstance(data, Mapping):
        lines = (
            [str(data["message"])] if "message" in data else ([title] if title else [])
        )
        lines += [
            f"{key}: {_plain(key, item)}"
            for key, item in data.items()
            if key != "message"
        ]
        return "\n".join(lines)
    if isinstance(data, list) and not data:
        return empty
    if isinstance(data, list) and all(isinstance(row, Mapping) for row in data):
        columns = list(dict.fromkeys(key for row in data for key in row))
        grid = [[c.upper() for c in columns]] + [
            [_plain(c, row.get(c)) for c in columns] for row in data
        ]
        widths = [max(len(line[i]) for line in grid) for i in range(len(columns))]
        return "\n".join(
            "  ".join(
                cell.ljust(width) for cell, width in zip(line, widths, strict=True)
            ).rstrip()
            for line in grid
        )
    if isinstance(data, list):
        return "\n".join(str(item) for item in data)
    return str(data)


def render_json(value: Result) -> str:
    """The result as indented JSON."""
    return json.dumps(to_data(value), indent=2, ensure_ascii=False)


def emit(
    value: Result,
    *,
    title: str | None = None,
    empty: str = "Nothing to show.",
    failed: bool = False,
) -> None:
    """Show a result on stdout in the chosen format."""
    match resolved_format():
        case OutputFormat.JSON:
            print(render_json(value), flush=True)
        case OutputFormat.RICH:
            render_rich(
                Console(soft_wrap=True),
                value,
                title=title,
                empty=empty,
                failed=failed,
            )
        case _:
            print(render_text(value, title=title, empty=empty), flush=True)


def emit_result(result: object) -> int:
    """Show whatever a command returned, and give back its exit status.

    A command that returns nothing (`serve`, `worker`) shows nothing.
    """
    if result is None:
        return 0
    if isinstance(result, Report):
        emit(
            result.value,
            title=result.title,
            empty=result.empty,
            failed=bool(result.exit_code),
        )
        return result.exit_code
    emit(result)
    return 0


# Show the result, then exit non-zero if the command asked to.
RESULT_ACTION: list[Any] = [emit_result, "sys_exit_if_non_zero_else_return"]
