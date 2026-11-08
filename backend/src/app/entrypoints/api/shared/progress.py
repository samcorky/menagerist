"""Composition of progress reporters, shared by every entrypoint and module adapter."""

from typing import TYPE_CHECKING

from app.platform.progress import log_sink_error
from app.shared_kernel.progress import CompositeProgressSink, SnapshotReporter

if TYPE_CHECKING:
    from app.shared_kernel.progress import ProgressSink


def make_reporter(*sinks: ProgressSink) -> SnapshotReporter:
    """A reporter that fans out to `sinks` and logs any sink that fails."""
    return SnapshotReporter(
        CompositeProgressSink(*sinks, on_error=log_sink_error),
        on_error=log_sink_error,
    )
