from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class CheckStatus(StrEnum):
    """Pass/fail result of a single readiness observation."""

    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


@dataclass(frozen=True, kw_only=True)
class CheckObservation:
    """A single measured readiness observation (health-check draft terminology)."""

    component_type: str
    observed_value: float | str
    observed_unit: str
    status: CheckStatus
    time: datetime
    output: str | None = None


@dataclass(frozen=True, kw_only=True)
class ReadinessReport:
    """Aggregate readiness result, keyed by `component:metric`."""

    status: CheckStatus
    checks: dict[str, list[CheckObservation]]
