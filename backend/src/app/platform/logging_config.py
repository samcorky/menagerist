import logging
import os
import sys
import uuid

import structlog

from app.platform.config import get_logging_settings


def _serialise_uuids(
    logger: logging.Logger | None,
    method_name: str,
    event_dict: structlog.types.EventDict,
) -> structlog.types.EventDict:
    """Coerce any uuid.UUID values in the event dict to strings."""
    return {
        key: str(value) if isinstance(value, uuid.UUID) else value
        for key, value in event_dict.items()
    }


def _expand_access_log_fields(
    logger: logging.Logger | None,
    method_name: str,
    event_dict: structlog.types.EventDict,
) -> structlog.types.EventDict:
    """Promote Granian's per-request access log fields to top-level keys."""
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
        # Granian names header atoms positionally (_h0, _h1, …). _h0 is
        # the Request-Id header — the only header atom in GRANIAN_ACCESS_LOG_FORMAT.
        # Granian emits "-" for a missing header (same convention as nginx).
        request_id = event_dict.pop("_h0", None)
        if request_id and request_id != "-":
            event_dict["request_id"] = request_id
        event_dict["event"] = f"{args['method']} {args['path']}"
        # Redundant with the `timestamp` key TimeStamper adds to every record.
        event_dict.pop("time", None)
    return event_dict


_configured = False


def configure_logging(*, level: int | str | None = None) -> None:
    """Sets up logging with structlog.

    A no-op on repeat calls unless `level` is given explicitly. Both entrypoint
    modules (`api`, `cli`) call this unconditionally at import time, and a CLI
    command can lazily import `api` after the CLI has already configured
    logging (e.g. via `--verbose`); without this guard, that later import-time
    call would silently reset the level back to `LOG_LEVEL`.
    """
    global _configured
    if _configured and level is None:
        return
    _configured = True

    settings = get_logging_settings()
    effective_level = level if level is not None else settings.log_level
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        _serialise_uuids,
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

    # Route warnings through logging handler.
    logging.captureWarnings(True)

    # Suppress verbose Alembic migration and plugin-registration logs.
    logging.getLogger("alembic.runtime.migration").setLevel(logging.WARNING)
    logging.getLogger("alembic.runtime.plugins").setLevel(logging.WARNING)

    # SQLAlchemy engine logs (SQL statements, result rows) are only useful when
    # actively debugging; suppress them unless the app itself is running at DEBUG.
    if root_logger.level > logging.DEBUG:
        logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


# Propagate Granian loggers to root so they render via structlog.
type LoggerConfig = dict[str, str | bool | list[str]]

# Granian access log format including Request-Id header.
GRANIAN_ACCESS_LOG_FORMAT = (
    '[%(time)s] %(addr)s - "%(method)s %(path)s %(protocol)s"'
    + " %(status)d %(dt_ms).3f %(header{request-id})s"
)


def granian_log_dictconfig() -> dict[str, dict[str, LoggerConfig]]:
    """Return the logging dictConfig fragment passed to Granian at server start.

    SQLAlchemy engine logs are only enabled when the configured log level is DEBUG,
    matching the suppression applied by configure_logging() for the non-Granian path.
    """
    settings = get_logging_settings()
    numeric_level = logging.getLevelName(settings.log_level.upper())
    sqlalchemy_level = (
        "DEBUG"
        if isinstance(numeric_level, int) and numeric_level <= logging.DEBUG
        else "WARNING"
    )
    return {
        "loggers": {
            "_granian": {"level": "INFO", "handlers": [], "propagate": True},
            "granian.access": {"level": "INFO", "handlers": [], "propagate": True},
            "sqlalchemy.engine": {
                "level": sqlalchemy_level,
                "handlers": [],
                "propagate": True,
            },
        },
    }
