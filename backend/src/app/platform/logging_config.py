import logging
import os
import sys

import structlog

from app.platform.config import get_logging_settings


def _expand_access_log_fields(
    logger: logging.Logger | None,
    method_name: str,
    event_dict: structlog.types.EventDict,
) -> structlog.types.EventDict:
    """Promote Granian's per-request access log fields to top-level keys.

    Granian builds a dict of request fields (addr, method, path, status,
    dt_ms, ...) and passes it as the log record's args - see
    granian.log.log_request_builder. With `pass_foreign_args=True` on the
    formatter below, that dict survives as `positional_args`. Merge it into
    the event dict so each field renders separately instead of being baked
    into one opaque message string via the access-log format template.
    """
    record: logging.LogRecord | None = event_dict.get("_record")
    args = event_dict.pop("positional_args", None)
    if (
        record is not None
        and record.name == "granian.access"
        and isinstance(args, dict)
    ):
        event_dict.update(args)
        # ASGI query strings are raw bytes; decode for a readable log field.
        query_string = event_dict.get("query_string")
        if isinstance(query_string, bytes):
            event_dict["query_string"] = query_string.decode("utf-8", "replace")
        event_dict["event"] = f"{args['method']} {args['path']}"
        # Redundant with the `timestamp` key TimeStamper adds to every record.
        event_dict.pop("time", None)
    return event_dict


def configure_logging(*, level: int | str | None = None) -> None:
    """Sets up logging with structlog."""
    settings = get_logging_settings()
    effective_level = level if level is not None else settings.log_level
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        _expand_access_log_fields,
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

    if settings.log_json:
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
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
        processor=renderer,
        foreign_pre_chain=shared_processors,
        pass_foreign_args=True,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    root_logger = logging.getLogger()
    root_logger.handlers.clear()  # avoid duplicate lines if this ever runs twice
    root_logger.addHandler(handler)
    root_logger.setLevel(effective_level)

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
