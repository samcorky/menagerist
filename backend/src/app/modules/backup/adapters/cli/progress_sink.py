"""Draw progress snapshots as an overall bar on a terminal."""

from contextlib import contextmanager
from typing import TYPE_CHECKING

from app.platform.cli_progress import overall_bar

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from app.shared_kernel.progress import ProgressSink, ProgressSnapshot


def describe(snapshot: ProgressSnapshot) -> str:
    """One line for the bar: the running phase, its counts and any message."""
    if snapshot.outcome == "failed":
        return f"Failed: {snapshot.message}" if snapshot.message else "Failed"
    if snapshot.outcome == "succeeded":
        return "Done"
    running = next((p for p in snapshot.phases if p.state == "running"), None)
    if running is None:
        return snapshot.message or "Starting"
    text = running.label
    if running.unit == "count" and running.total is not None:
        text += f" ({running.done:,} of {running.total:,})"
    return f"{text}: {snapshot.message}" if snapshot.message else text


class RichProgressSink:
    """Moves the terminal bar to each snapshot's percentage and phase."""

    def __init__(self, update: Callable[[int, str], None]) -> None:
        self._update = update

    async def write(self, snapshot: ProgressSnapshot) -> None:
        """Redraw the bar for `snapshot`."""
        self._update(snapshot.percent, describe(snapshot))


@contextmanager
def snapshot_display() -> Iterator[ProgressSink | None]:
    """Yield a sink that draws the bar, or None when nobody is watching."""
    with overall_bar() as update:
        yield None if update is None else RichProgressSink(update)
