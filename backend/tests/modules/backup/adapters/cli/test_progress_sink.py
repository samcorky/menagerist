"""The backup CLI draws progress snapshots as a terminal bar."""

import io

import pytest
from rich.console import Console

from app.modules.backup.adapters.cli.progress_sink import describe, snapshot_display
from app.platform import cli_progress
from app.shared_kernel.progress import PhaseState, ProgressSnapshot


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


def snapshot(**overrides: object) -> ProgressSnapshot:
    """A restore part-way through the photos."""
    phases = (
        PhaseState(key="verify", label="Checking", state="done", done=9, total=9),
        PhaseState(
            key="media",
            label="Restoring photos",
            state="running",
            done=1240,
            total=2000,
        ),
        PhaseState(key="x", label="Later", state="waiting", done=0, total=None),
    )
    values: dict[str, object] = {
        "phases": phases,
        "message": None,
        "percent": 62,
        "outcome": "running",
    }
    return ProgressSnapshot(**{**values, **overrides})  # type: ignore[arg-type]


def test_no_sink_without_a_terminal() -> None:
    """Pipes, cron and tests get None, so nothing is drawn."""
    with snapshot_display() as sink:
        assert sink is None


async def test_the_bar_names_the_running_phase_with_counts(
    terminal: io.StringIO,
) -> None:
    """A counted phase shows how many of how many."""
    with snapshot_display() as sink:
        assert sink is not None
        await sink.write(snapshot())
    assert "Restoring photos (1,240 of 2,000)" in terminal.getvalue()
    assert "62%" in terminal.getvalue()


async def test_a_byte_phase_shows_no_counts(terminal: io.StringIO) -> None:
    """Bytes mean nothing to a person, so only the percentage is drawn."""
    phase = PhaseState(
        key="verify", label="Checking", state="running", done=5, total=9, unit="bytes"
    )
    with snapshot_display() as sink:
        assert sink is not None
        await sink.write(snapshot(phases=(phase,)))
    assert "Checking" in terminal.getvalue()
    assert " of 9" not in terminal.getvalue()


async def test_a_message_follows_the_phase(terminal: io.StringIO) -> None:
    """A message says what is happening inside the phase."""
    with snapshot_display() as sink:
        assert sink is not None
        await sink.write(snapshot(message="Reading photos"))
    assert "Restoring photos (1,240 of 2,000): Reading photos" in terminal.getvalue()


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"outcome": "succeeded"}, "Done"),
        ({"outcome": "failed", "message": "Damaged"}, "Failed: Damaged"),
        ({"outcome": "failed"}, "Failed"),
        ({"phases": (), "message": "Hold on"}, "Hold on"),
        ({"phases": ()}, "Starting"),
    ],
)
def test_the_description_covers_every_outcome(
    overrides: dict[str, object], expected: str
) -> None:
    """The line under the bar reads sensibly before, during and after the run."""
    assert describe(snapshot(**overrides)) == expected
