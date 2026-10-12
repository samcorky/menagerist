from typing import TYPE_CHECKING

import structlog

from app.modules.system.domain.readiness import CheckObservation, CheckStatus

if TYPE_CHECKING:
    from datetime import datetime

logger = structlog.get_logger()


def observation(
    observed_value: float | str,
    observed_unit: str,
    *,
    now: datetime,
    status: CheckStatus = CheckStatus.PASS,
    output: str | None = None,
) -> CheckObservation:
    """Build a passing/warning/failing observation for the given metric."""
    return CheckObservation(
        component_type="datastore",
        observed_value=observed_value,
        observed_unit=observed_unit,
        status=status,
        time=now,
        output=output,
    )


def failed_observation(unit: str, *, now: datetime, exc: Exception) -> CheckObservation:
    """Build a failed observation; the real error is logged, never returned."""
    logger.error("readiness check failed", unit=unit, exc_info=exc)
    return observation(
        "unknown", unit, now=now, status=CheckStatus.FAIL, output="check failed"
    )
