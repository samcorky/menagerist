"""The production reporter fans out to sinks and logs the ones that fail."""

from structlog.testing import capture_logs

from app.entrypoints.api.shared.progress import make_reporter
from app.platform.progress import log_sink_error
from app.shared_kernel.progress import Phase, ProgressSnapshot


class ListSink:
    """Collects every snapshot written to it."""

    def __init__(self) -> None:
        self.written: list[ProgressSnapshot] = []

    async def write(self, snapshot: ProgressSnapshot) -> None:
        """Keep the snapshot."""
        self.written.append(snapshot)


class BrokenSink:
    """A sink whose every write fails."""

    async def write(self, snapshot: ProgressSnapshot) -> None:
        """Fail."""
        raise OSError("disk full")


async def test_the_reporter_writes_to_each_sink_and_logs_failures() -> None:
    """A broken sink is logged as a warning while a healthy one keeps receiving."""
    healthy = ListSink()
    reporter = make_reporter(BrokenSink(), healthy)
    with capture_logs() as logs:
        await reporter.begin((Phase(key="a", label="A"),))
        await reporter.done()
    assert len(healthy.written) == 2
    assert [log["event"] for log in logs].count("progress write failed") == 2


def test_log_sink_error_logs_a_warning() -> None:
    """The error hook records the failure at warning level."""
    with capture_logs() as logs:
        log_sink_error(OSError("nope"))
    assert [(log["event"], log["log_level"]) for log in logs] == [
        ("progress write failed", "warning")
    ]
