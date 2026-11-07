"""Logging for progress writes that fail."""

import structlog

logger = structlog.get_logger()


def log_sink_error(error: Exception) -> None:
    """Record a failed progress write; the operation it reports on carries on."""
    logger.warning("progress write failed", exc_info=error)
