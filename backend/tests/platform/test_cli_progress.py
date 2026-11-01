import io
from typing import TYPE_CHECKING

import pytest
from rich.console import Console

from app.platform import cli_progress
from app.platform.cli_progress import activity, byte_progress, confirm, interactive

if TYPE_CHECKING:
    from collections.abc import Callable


@pytest.fixture
def terminal(monkeypatch: pytest.MonkeyPatch) -> io.StringIO:
    """Pretend a person is at a terminal, and capture what is drawn on stderr."""
    sink = io.StringIO()
    monkeypatch.setattr(cli_progress, "interactive", lambda: True)
    monkeypatch.setattr(
        cli_progress,
        "_console",
        lambda: Console(file=sink, force_terminal=True, width=100),
    )
    return sink


def test_nothing_is_drawn_without_a_terminal(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Under pytest, in a pipe or in cron there is no spinner or bar."""
    assert interactive() is False
    with activity("Working"):
        pass
    with byte_progress("Copying", 10) as advance:
        advance(10)
    captured = capsys.readouterr()
    assert (captured.out, captured.err) == ("", "")


def test_a_dumb_terminal_is_not_interactive(monkeypatch: pytest.MonkeyPatch) -> None:
    """Even a tty cannot redraw when `TERM=dumb`."""
    monkeypatch.setattr("sys.stderr.isatty", lambda: True, raising=False)
    monkeypatch.setenv("TERM", "dumb")
    assert interactive() is False
    monkeypatch.setenv("TERM", "xterm")
    assert interactive() is True


def test_a_spinner_names_the_step(terminal: io.StringIO) -> None:
    """The description is shown while the step runs."""
    with activity("Restoring the backup"):
        pass
    assert "Restoring the backup" in terminal.getvalue()


def test_a_bar_reports_finished_bytes(terminal: io.StringIO) -> None:
    """Advancing fills the bar and shows sizes."""
    with byte_progress("Downloading", 2048) as advance:
        advance(2048)
    assert "Downloading" in terminal.getvalue()
    assert "2.0/2.0 kB" in terminal.getvalue()


def test_scripts_are_never_asked(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without a terminal on both ends the command goes ahead."""

    def refuse(*_args: object, **_kwargs: object) -> bool:
        pytest.fail("asked")

    monkeypatch.setattr("app.platform.cli_progress.Confirm.ask", refuse)
    confirm("Delete it?")


def test_yes_skips_the_question(
    terminal: io.StringIO, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--yes` is for people who already know."""
    monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)

    def refuse(*_args: object, **_kwargs: object) -> bool:
        pytest.fail("asked")

    monkeypatch.setattr("app.platform.cli_progress.Confirm.ask", refuse)
    confirm("Delete it?", assume_yes=True)


@pytest.mark.parametrize("answer", [True, False])
def test_a_person_can_decline(
    terminal: io.StringIO, monkeypatch: pytest.MonkeyPatch, answer: bool
) -> None:
    """A no stops the command with a clear message and a non-zero exit."""
    monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)
    asked: list[str] = []

    def ask(question: str, **_kwargs: object) -> bool:
        asked.append(question)
        return answer

    monkeypatch.setattr("app.platform.cli_progress.Confirm.ask", ask)
    if answer:
        confirm("Delete it?")
    else:
        with pytest.raises(SystemExit, match="Cancelled"):
            confirm("Delete it?")
    assert asked == ["Delete it?"]


def test_the_callable_type_is_usable() -> None:
    """The bar's advance function is a plain callable of a byte count."""
    with byte_progress("x", 1) as advance:
        typed: Callable[[int], None] = advance
        typed(1)
