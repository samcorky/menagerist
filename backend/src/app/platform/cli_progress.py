"""Spinners, progress bars and confirmations for people at a terminal.

All of it goes to stderr and only appears when a person is there: stdout stays a
command's result, and pipes, cron, `--json` and tests see none of it.
"""

import sys
from contextlib import contextmanager
from typing import TYPE_CHECKING

from rich.console import Console
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.prompt import Confirm

from app.platform.config.terminal import get_terminal_settings

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator


def interactive() -> bool:
    """Whether a person is watching stderr on a terminal that can redraw."""
    return sys.stderr.isatty() and not get_terminal_settings().is_dumb


def _console() -> Console:
    return Console(stderr=True)


@contextmanager
def activity(description: str) -> Iterator[None]:
    """Show a spinner with the time taken while a step with no known length runs."""
    if not interactive():
        yield
        return
    with _console().status(f"{description}…", spinner="dots"):
        yield


@contextmanager
def byte_progress(description: str, total: int) -> Iterator[Callable[[int], None]]:
    """Show a bar with speed and time left; the yielded callable adds finished bytes."""
    if not interactive():
        yield lambda _count: None
        return
    with Progress(
        TextColumn("{task.description}"),
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        console=_console(),
        transient=True,
    ) as progress:
        task = progress.add_task(description, total=total)
        yield lambda count: progress.advance(task, count)


@contextmanager
def overall_bar() -> Iterator[Callable[[int, str], None] | None]:
    """Yield `update(percent, description)` for a bar out of 100, or None.

    None means nobody is watching, so a caller skips drawing altogether.
    """
    if not interactive():
        yield None
        return
    # The spinner turns on its own refresh, so a step that reports nothing for a
    # while (a long database statement) still shows that the run is alive.
    with Progress(
        SpinnerColumn("dots"),
        TextColumn("{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=_console(),
        transient=True,
    ) as progress:
        task = progress.add_task("Starting", total=100)
        yield lambda percent, description: progress.update(
            task, completed=percent, description=description
        )


def confirm(question: str, *, assume_yes: bool = False) -> None:
    """Ask before something destructive, and stop if the answer is no.

    Scripts are never asked: with `--yes`, or without a terminal on both ends, the
    command goes ahead as it always has.
    """
    if assume_yes or not (interactive() and sys.stdin.isatty()):
        return
    if not Confirm.ask(question, console=_console(), default=False):
        raise SystemExit("Cancelled.")
