from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.shared_kernel.cqrs import UseCase

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True)
class GetHealthQuery:
    """Request for a liveness check."""


class GetHealth(UseCase[GetHealthQuery, None]):
    """Report that the process is up and able to accept requests."""

    async def handle(self, query: GetHealthQuery, actor: Actor) -> None:
        """Liveness has no dependencies to check — succeeding is the signal."""
        return None
