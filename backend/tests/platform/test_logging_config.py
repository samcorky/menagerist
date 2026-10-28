import logging
import sys
from typing import TYPE_CHECKING

import pytest
import structlog

from app.platform import logging_config
from app.platform.config import LoggingSettings, LogLevel
from app.platform.logging_config import configure_logging

if TYPE_CHECKING:
    from collections.abc import Iterator

_NAMED_LOGGERS = (
    "alembic.runtime.migration",
    "alembic.runtime.plugins",
    "markdown_it",
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


@pytest.mark.parametrize(
    ("sqlalchemy_level", "expected_level"),
    [
        ("WARNING", logging.WARNING),
        ("info", logging.INFO),
        ("debug", logging.DEBUG),
    ],
)
def test_sqlalchemy_level_is_independent_of_application_level(
    monkeypatch: pytest.MonkeyPatch,
    sqlalchemy_level: LogLevel | str,
    expected_level: int,
) -> None:
    """SQLAlchemy's logger level is set independently of the root logger."""
    monkeypatch.setattr(
        logging_config,
        "get_logging_settings",
        lambda: LoggingSettings(sqlalchemy_level=sqlalchemy_level),
    )

    configure_logging()

    assert logging.getLogger().level == logging.INFO
    assert logging.getLogger("sqlalchemy.engine").level == expected_level


@pytest.mark.parametrize("sqlalchemy_level", ["WARNING", "info", "debug"])
def test_granian_uses_configured_sqlalchemy_level(
    monkeypatch: pytest.MonkeyPatch,
    sqlalchemy_level: str,
) -> None:
    """Granian receives the same independent SQLAlchemy logger level."""
    monkeypatch.setattr(
        logging_config,
        "get_logging_settings",
        lambda: LoggingSettings(sqlalchemy_level=sqlalchemy_level),
    )

    loggers = logging_config.granian_log_dictconfig()["loggers"]

    assert loggers["sqlalchemy.engine"]["level"] == sqlalchemy_level.upper()


@pytest.mark.parametrize(
    ("log_level", "sqlalchemy_log_level"),
    [("debug", "info"), ("DEBUG", "INFO")],
)
def test_logging_settings_accept_uppercase_and_lowercase_values(
    log_level: str,
    sqlalchemy_log_level: str,
) -> None:
    """Both logging settings accept either casing for enum values."""
    settings = LoggingSettings(
        level=log_level,
        sqlalchemy_level=sqlalchemy_log_level,
    )

    assert settings.level is LogLevel.DEBUG
    assert settings.sqlalchemy_level is LogLevel.INFO


def test_markdown_it_stays_quiet_even_when_the_application_logs_debug() -> None:
    """Its per-rule debug lines would drown real output, whatever the app level is."""
    configure_logging(level="DEBUG")
    assert logging.getLogger().isEnabledFor(logging.DEBUG)
    for name in ("markdown_it", "markdown_it.rules_block.paragraph"):
        logger = logging.getLogger(name)
        assert not logger.isEnabledFor(logging.DEBUG)
        assert logger.isEnabledFor(logging.WARNING)


def test_logs_can_be_sent_to_stderr_to_keep_stdout_for_output(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A CLI that prints data asks for stderr, so `command | jq` stays valid."""
    configure_logging(level="ERROR", stream=sys.stderr)
    logger = structlog.get_logger("test")
    logger.info("quiet progress")
    logger.error("something failed")
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "something failed" in captured.err
    assert "quiet progress" not in captured.err


def test_logs_go_to_stdout_by_default(capsys: pytest.CaptureFixture[str]) -> None:
    """The server's logs stay on stdout, where a container collects them."""
    configure_logging(level="INFO")
    structlog.get_logger("test").info("hello")
    captured = capsys.readouterr()
    assert "hello" in captured.out
    assert captured.err == ""
