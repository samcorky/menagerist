"""A database outage is a one-line warning; other check failures keep the traceback."""

import socket
from datetime import UTC, datetime

from structlog.testing import capture_logs

from app.modules.system.adapters.platform.checks._util import failed_observation

NOW = datetime(2026, 10, 28, tzinfo=UTC)


def test_database_outage_logs_a_warning_without_a_traceback() -> None:
    """An unreachable database must not fill the log with a traceback per probe."""
    with capture_logs() as logs:
        failed_observation("ms", now=NOW, exc=socket.gaierror(-2, "unknown host"))

    (entry,) = logs
    assert entry["log_level"] == "warning"
    assert entry["error"] == "gaierror"
    assert "exc_info" not in entry


def test_other_failures_still_log_the_traceback() -> None:
    """Anything that is not an outage is a bug worth the full error."""
    error = RuntimeError("boom")
    with capture_logs() as logs:
        failed_observation("ms", now=NOW, exc=error)

    (entry,) = logs
    assert entry["log_level"] == "error"
    assert entry["exc_info"] is error
