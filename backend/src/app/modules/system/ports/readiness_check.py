from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Mapping

    from app.modules.system.domain.readiness import CheckObservation


class ReadinessCheck(Protocol):
    """A single pluggable readiness probe.

    Returns one or more keyed observations (`component:metric` -> observation) — a
    check may cover several metrics at once when they share a resource, e.g. a
    database connectivity check reusing one session for responseTime and version.
    """

    async def run(self) -> Mapping[str, CheckObservation]:
        """Run the probe and return its keyed observation(s)."""
        ...
