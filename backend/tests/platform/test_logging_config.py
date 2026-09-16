import logging

import pytest

from app.platform import logging_config
from app.platform.logging_config import configure_logging


@pytest.fixture(autouse=True)
def _reset_configured_flag() -> None:
    """Isolate `_configured` per test so runs don't depend on import order."""
    logging_config._configured = False


def test_repeat_call_without_level_does_not_reset_an_explicit_level() -> None:
    """A later import-time `configure_logging()` must not undo `--verbose`.

    Regression test: `api` and `cli` both call `configure_logging()` at import
    time. A CLI command that lazily imports `api` after `--verbose` has already
    set DEBUG was silently resetting the root logger back to `LOG_LEVEL`.
    """
    configure_logging(level=logging.DEBUG)
    configure_logging()

    assert logging.getLogger().level == logging.DEBUG


def test_first_call_applies_the_default_level() -> None:
    """The first call in a process still configures the default `LOG_LEVEL`."""
    configure_logging()

    assert logging.getLogger().level == logging.INFO


def test_explicit_level_always_reapplies() -> None:
    """An explicit `level` always takes effect, even on a repeat call."""
    configure_logging()
    configure_logging(level=logging.WARNING)

    assert logging.getLogger().level == logging.WARNING
