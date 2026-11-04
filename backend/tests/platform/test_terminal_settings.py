"""The standard terminal variables are read through `TerminalSettings`."""

import pytest

from app.platform.config.terminal import get_terminal_settings


@pytest.mark.parametrize(
    ("term", "dumb"), [("dumb", True), ("xterm-256color", False), (None, False)]
)
def test_term_dumb_means_the_terminal_cannot_redraw(
    monkeypatch: pytest.MonkeyPatch, term: str | None, dumb: bool
) -> None:
    """Only the exact value `dumb` disables redrawing."""
    if term is None:
        monkeypatch.delenv("TERM", raising=False)
    else:
        monkeypatch.setenv("TERM", term)
    assert get_terminal_settings().is_dumb is dumb


@pytest.mark.parametrize(
    ("value", "colour"),
    [(None, True), ("", True), ("0", True), ("00", True), ("1", False), ("yes", False)],
)
def test_no_color_turns_colour_off_unless_empty_or_zero(
    monkeypatch: pytest.MonkeyPatch, value: str | None, colour: bool
) -> None:
    """An empty `NO_COLOR` is unset, as no-color.org says, and used to raise."""
    if value is None:
        monkeypatch.delenv("NO_COLOR", raising=False)
    else:
        monkeypatch.setenv("NO_COLOR", value)
    assert get_terminal_settings().colour is colour


def test_the_prefixed_names_are_not_read(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only the standard names count; `MENAGERIST_TERMINAL_TERM` means nothing."""
    monkeypatch.delenv("TERM", raising=False)
    monkeypatch.setenv("MENAGERIST_TERMINAL_TERM", "dumb")
    assert get_terminal_settings().is_dumb is False
