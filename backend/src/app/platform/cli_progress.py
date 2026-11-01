"""Spinners, progress bars and confirmations for people at a terminal.

All of it goes to stderr and only appears when a person is there: stdout stays a
command's result, and pipes, cron, `--json` and tests see none of it.
"""

import os
import sys
from contextlib import contextmanager
from typing import TYPE_CHECKING

from rich.console import Console
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.prompt import Confirm

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator


def interactive() -> bool:
    """Whether a person is watching stderr on a terminal that can redraw."""
    return sys.stderr.isatty() and os.environ.get("TERM") != "dumb"


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


def confirm(question: str, *, assume_yes: bool = False) -> None:
    """Ask before something destructive, and stop if the answer is no.

    Scripts are never asked: with `--yes`, or without a terminal on both ends, the
    command goes ahead as it always has.
    """
    if assume_yes or not (interactive() and sys.stdin.isatty()):
        return
    if not Confirm.ask(question, console=_console(), default=False):
        raise SystemExit("Cancelled.")
