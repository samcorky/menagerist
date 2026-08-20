import logging
import os
import sys

import structlog


def configure_logging(*, level: int | str = logging.INFO) -> None:
    """Sets up logging with structlog."""
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # https://no-color.org/
    colors_enabled = os.environ.get("NO_COLOR", "0")[0] == "0"
    renderer = structlog.dev.ConsoleRenderer(
        colors=colors_enabled,
        # On Windows, colorama strips ANSI codes whenever stdout isn't a real
        # console handle - which is always the case when poe pipes a task's
        # output (eg. `parallel`) to prefix each line. force_colors keeps the
        # codes intact in that case too.
        force_colors=colors_enabled,
        sort_keys=False,
    )
    formatter = structlog.stdlib.ProcessorFormatter(
        processor=renderer, foreign_pre_chain=shared_processors
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    root_logger = logging.getLogger()
    root_logger.handlers.clear()  # avoid duplicate lines if this ever runs twice
    root_logger.addHandler(handler)
    root_logger.setLevel(level)

    # Route warnings.warn() (deprecation warnings from dependencies, etc.)
    # through logging -> the same handler above, instead of straight to stderr.
    logging.captureWarnings(True)


# Handed to Granian's `log_dictconfig` param. Granian's own `_granian` and
# `granian.access` loggers default to `propagate: False` with their own
# plain-text handlers, which bypasses the structlog renderer entirely.
# This strips their handlers and lets records propagate to root instead,
# so server startup/lifecycle and access logs render identically to
# everything else.
type LoggerConfig = dict[str, str | bool | list[str]]

GRANIAN_LOG_DICTCONFIG: dict[str, dict[str, LoggerConfig]] = {
    "loggers": {
        "_granian": {"level": "INFO", "handlers": [], "propagate": True},
        "granian.access": {"level": "INFO", "handlers": [], "propagate": True},
    },
}
