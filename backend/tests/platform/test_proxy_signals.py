from datetime import UTC, datetime, timedelta

import pytest
import structlog
from structlog.testing import capture_logs

from app.platform import proxy_signals
from app.platform.proxy_signals import ProxySignal


@pytest.fixture(autouse=True)
def _clean(monkeypatch: pytest.MonkeyPatch) -> None:
    proxy_signals.reset()
    # The app caches its loggers on first use; a fresh one can be captured.
    monkeypatch.setattr(proxy_signals, "logger", structlog.get_logger())


def test_nothing_is_counted_until_a_signal_is_recorded() -> None:
    """A fresh process has seen nothing."""
    assert set(proxy_signals.counts().values()) == {0}


def test_counts_each_signal_separately() -> None:
    """Each signal has its own tally."""
    proxy_signals.record(ProxySignal.UNTRUSTED_FORWARDING)
    proxy_signals.record(ProxySignal.UNTRUSTED_FORWARDING)
    proxy_signals.record(ProxySignal.ORIGIN_MISMATCH)

    counts = proxy_signals.counts()

    assert counts[ProxySignal.UNTRUSTED_FORWARDING] == 2
    assert counts[ProxySignal.ORIGIN_MISMATCH] == 1


def test_only_the_last_hour_counts() -> None:
    """Older sightings drop out of the count."""
    now = datetime.now(UTC)
    proxy_signals.record(
        ProxySignal.ORIGIN_MISMATCH,
        now=now - proxy_signals.WINDOW - timedelta(seconds=1),
    )
    proxy_signals.record(ProxySignal.ORIGIN_MISMATCH, now=now - timedelta(minutes=5))

    assert proxy_signals.counts(now=now)[ProxySignal.ORIGIN_MISMATCH] == 1


def test_memory_is_bounded() -> None:
    """A flood of requests keeps a bounded number of times."""
    for _ in range(1500):
        proxy_signals.record(ProxySignal.ORIGIN_MISMATCH)

    assert proxy_signals.counts()[ProxySignal.ORIGIN_MISMATCH] == 1000


def test_the_first_sighting_in_a_window_is_logged_once_with_the_fix() -> None:
    """The log shows the problem and what to set, without a line per request."""
    with capture_logs() as logs:
        proxy_signals.record(ProxySignal.UNTRUSTED_FORWARDING)
        proxy_signals.record(ProxySignal.UNTRUSTED_FORWARDING)
        proxy_signals.record(ProxySignal.ORIGIN_MISMATCH)

    warnings = [e for e in logs if e["log_level"] == "warning"]
    assert [w["signal"] for w in warnings] == [
        "untrusted_forwarding",
        "origin_mismatch",
    ]
    assert "MENAGERIST_TRUSTED_PROXIES" in warnings[0]["hint"]


def test_a_signal_is_logged_again_after_the_window() -> None:
    """A problem that persists reminds the operator once an hour."""
    now = datetime.now(UTC)
    proxy_signals.record(
        ProxySignal.ORIGIN_MISMATCH,
        now=now - proxy_signals.WINDOW - timedelta(seconds=1),
    )

    with capture_logs() as logs:
        proxy_signals.record(ProxySignal.ORIGIN_MISMATCH, now=now)

    assert len(logs) == 1
