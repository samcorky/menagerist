import logging
from typing import TYPE_CHECKING

import pytest
import structlog

from app.platform import logging_config
from app.platform.logging_config import configure_logging

if TYPE_CHECKING:
    from collections.abc import Iterator

_NAMED_LOGGERS = (
    "alembic.runtime.migration",
    "alembic.runtime.plugins",
    "sqlalchemy.engine",
)


@pytest.fixture(autouse=True)
def _isolate_logging_state() -> Iterator[None]:
    """Give each test a fresh `_configured` flag and undo what it changes globally.

    `configure_logging` rewrites the root logger, structlog and a few named
    loggers; left behind, that leaks into whichever test runs next.
    """
    root = logging.getLogger()
    named = [logging.getLogger(n) for n in _NAMED_LOGGERS]
    saved_root = (root.level, list(root.handlers))
    saved_named = [(lg, lg.level) for lg in named]
    saved_structlog = structlog.get_config()
    logging_config._configured = False
    yield
    root.setLevel(saved_root[0])
    root.handlers[:] = saved_root[1]
    for lg, level in saved_named:
        lg.setLevel(level)
    structlog.configure(**saved_structlog)
    logging.captureWarnings(False)
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
