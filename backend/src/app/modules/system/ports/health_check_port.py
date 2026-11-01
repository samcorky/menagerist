from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from app.modules.system.domain.readiness import ReadinessReport


class HealthCheckPort(Protocol):
    """Verifies that the application's runtime dependencies are reachable."""

    async def check(self) -> ReadinessReport:
        """Run all readiness checks and return their aggregate result."""
        ...
