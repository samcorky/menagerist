import dataclasses
import json
import sys
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

import pytest
from cyclopts import App

from app.platform import cli_output
from app.platform.cli_output import (
    RESULT_ACTION,
    OutputFormat,
    Report,
    emit,
    emit_result,
    format_bytes,
    resolved_format,
    set_format,
    to_data,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

ID = UUID("01978c3e-2b8b-7c3a-9c2e-3a2f6b9d4e10")


class Colour(StrEnum):
    """A sample enumeration."""

    RED = "red"


@dataclasses.dataclass(frozen=True)
class Row:
    """A sample result row."""

    id: UUID
    colour: Colour
    size: int
    created_at: datetime
    tags: list[str]


@pytest.fixture(autouse=True)
def _reset_format() -> Iterator[None]:
    set_format(OutputFormat.AUTO)
    yield
    set_format(OutputFormat.AUTO)


def test_to_data_turns_results_into_plain_json_data() -> None:
    """Dataclasses, enums, ids, times, paths and sets all become JSON values."""
    row = Row(ID, Colour.RED, 5, datetime(2026, 10, 28, 15, tzinfo=UTC), ["b", "a"])
    assert to_data({"rows": [row], "path": Path("/data/x"), "ids": {"b", "a"}}) == {
        "rows": [
            {
                "id": str(ID),
                "colour": "red",
                "size": 5,
                "created_at": "2026-10-28T15:00:00+00:00",
                "tags": ["b", "a"],
            }
        ],
        "path": "/data/x",
        "ids": ["a", "b"],
    }
    assert to_data(("a", 1)) == ["a", 1]
    assert to_data("text") == "text"


def test_auto_is_rich_on_a_terminal_and_plain_text_otherwise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The default needs no flag, and JSON is never chosen for you."""
    monkeypatch.setenv("TERM", "xterm-256color")
    monkeypatch.setattr(sys.stdout, "isatty", lambda: False)
    assert resolved_format() is OutputFormat.TEXT
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    assert resolved_format() is OutputFormat.RICH
    monkeypatch.setenv("TERM", "dumb")
    assert resolved_format() is OutputFormat.TEXT


def test_an_explicit_format_wins_over_the_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`--json` on a terminal and `--format rich` in a pipe both do what they say."""
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    set_format(OutputFormat.JSON)
    assert resolved_format() is OutputFormat.JSON
    monkeypatch.setattr(sys.stdout, "isatty", lambda: False)
    set_format(OutputFormat.RICH)
    assert resolved_format() is OutputFormat.RICH
    set_format(OutputFormat.TEXT)
    assert resolved_format() is OutputFormat.TEXT


def test_json_output_is_valid_json_and_only_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Nothing but the result reaches stdout, so it can be piped to jq."""
    set_format(OutputFormat.JSON)
    emit({"message": "Done", "count": 3})
    assert json.loads(capsys.readouterr().out) == {"message": "Done", "count": 3}


def test_rich_shows_a_message_with_its_details(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A message is a tick and a sentence, with the rest as a field table."""
    set_format(OutputFormat.RICH)
    emit({"message": "Backup created", "id": "abc", "size": 1536, "verified": True})
    out = capsys.readouterr().out
    assert "✓ Backup created" in out
    assert "Id" in out
    assert "abc" in out
    assert "1.5 KiB" in out
    assert "yes" in out


def test_rich_shows_a_mapping_as_a_field_table_with_a_title(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Keys become labels and missing values a dash."""
    set_format(OutputFormat.RICH)
    emit({"freed_bytes": 2048, "kept": ["a", "b"], "note": None}, title="Prune report")
    out = capsys.readouterr().out
    assert "Prune report" in out
    assert "Freed bytes" in out
    assert "2.0 KiB" in out
    assert "a, b" in out
    assert "—" in out


def test_rich_shows_a_list_of_records_as_a_table(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Columns come from the records' keys, in order."""
    set_format(OutputFormat.RICH)
    emit([{"id": "1", "label": "manual"}, {"id": "2", "label": "scheduled"}])
    out = capsys.readouterr().out
    assert "Id" in out
    assert "Label" in out
    assert "scheduled" in out


def test_rich_says_so_when_there_is_nothing_to_show(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An empty list is a sentence, not a blank screen."""
    set_format(OutputFormat.RICH)
    emit([], empty="No backups yet.")
    assert "No backups yet." in capsys.readouterr().out


def test_rich_lists_plain_values_and_prints_scalars(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Lists of text are bullets; a bare string is printed as it is."""
    set_format(OutputFormat.RICH)
    emit(["alpha", "beta"])
    emit("just text")
    out = capsys.readouterr().out
    assert "• alpha" in out
    assert "• beta" in out
    assert "just text" in out


def test_rich_shows_nested_values_compactly(capsys: pytest.CaptureFixture[str]) -> None:
    """A nested mapping is one readable line, not a Python repr."""
    set_format(OutputFormat.RICH)
    emit({"counts": {"items": 2, "collections": 1}, "empty": {}})
    out = capsys.readouterr().out
    assert "Items: 2, Collections: 1" in out


@pytest.mark.parametrize(
    ("count", "text"),
    [
        (0, "0 B"),
        (1023, "1023 B"),
        (1024, "1.0 KiB"),
        (5 * 1024**2, "5.0 MiB"),
        (3 * 1024**3, "3.0 GiB"),
        (2048 * 1024**3, "2048.0 GiB"),
    ],
)
def test_format_bytes(count: int, text: str) -> None:
    """Sizes read as people write them."""
    assert format_bytes(count) == text


def _cli() -> App:
    """A small app wired like the real one."""
    cli = App(name="t", result_action=RESULT_ACTION)

    @cli.command
    def hello(name: str) -> dict[str, str]:
        """Say hello."""
        return {"hello": name}

    @cli.command
    def check() -> Report:
        """Fail with findings."""
        return Report(value={"findings": ["bad"]}, exit_code=1)

    @cli.command
    def listing() -> Report:
        """Show nothing."""
        return Report(value=[], empty="Nothing here.")

    @cli.command
    def quiet() -> None:
        """Long-running commands return nothing."""

    return cli


def test_a_returned_result_is_shown(capsys: pytest.CaptureFixture[str]) -> None:
    """The command returns; the root app shows it."""
    set_format(OutputFormat.JSON)
    _cli()(["hello", "world"], exit_on_error=False)
    assert json.loads(capsys.readouterr().out) == {"hello": "world"}


def test_a_failed_report_is_shown_and_then_the_command_exits(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A failed check prints what it found and still exits non-zero."""
    set_format(OutputFormat.JSON)
    with pytest.raises(SystemExit) as stopped:
        _cli()(["check"], exit_on_error=False)
    assert stopped.value.code == 1
    assert json.loads(capsys.readouterr().out) == {"findings": ["bad"]}


def test_a_report_carries_its_empty_text(capsys: pytest.CaptureFixture[str]) -> None:
    """An empty list says so instead of printing nothing."""
    _cli()(["listing"], exit_on_error=False)
    assert capsys.readouterr().out.strip() == "Nothing here."


def test_a_command_that_returns_nothing_prints_nothing(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`serve` and `worker` run until stopped and have no result."""
    assert emit_result(None) == 0
    _cli()(["quiet"], exit_on_error=False)
    assert capsys.readouterr().out == ""


def test_module_state_starts_automatic() -> None:
    """Nothing changes behaviour until a flag is given."""
    assert cli_output._format is OutputFormat.AUTO


def test_plain_text_is_the_default_when_piped(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """No colour, no box drawing, no JSON: lines a log or grep can use."""
    emit({"message": "Backup created", "id": "abc", "size": 1536, "verified": True})
    assert capsys.readouterr().out == (
        "Backup created\nid: abc\nsize: 1.5 KiB\nverified: yes\n"
    )


def test_plain_text_mapping_without_a_message_uses_the_title(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Fields are key: value lines, with a dash for nothing."""
    emit({"kept": ["a", "b"], "note": None, "freed_bytes": 0}, title="Prune report")
    assert capsys.readouterr().out == (
        "Prune report\nkept: a, b\nnote: -\nfreed_bytes: 0 B\n"
    )
    emit({"counts": {"items": 2}, "ids": []})
    assert capsys.readouterr().out == "counts: items=2\nids: -\n"


def test_plain_text_records_are_aligned_columns_with_a_header(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """One header line, then a line per record, columns padded to line up."""
    emit([{"id": "1", "label": "manual"}, {"id": "22", "label": "scheduled"}])
    assert capsys.readouterr().out == ("ID  LABEL\n1   manual\n22  scheduled\n")


def test_plain_text_lists_values_and_says_when_empty(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Plain values are one per line, and an empty result says so."""
    emit(["alpha", "beta"])
    emit([], empty="No backups yet.")
    emit("just text")
    assert capsys.readouterr().out == "alpha\nbeta\nNo backups yet.\njust text\n"
