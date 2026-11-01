from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from app.shared_kernel.access import Access, Public
from app.shared_kernel.access_guard import AccessGuard  # noqa: TC001
from app.shared_kernel.cqrs import UseCase

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True)
class GetHealthQuery:
    """Request for a liveness check."""


class GetHealth(UseCase[GetHealthQuery, None]):
    """Report that the process is up and able to accept requests."""

    access: ClassVar[Access] = Public()

    def __init__(self, guard: AccessGuard) -> None:
        self._guard = guard

    async def _handle(self, query: GetHealthQuery, actor: Actor) -> None:
        """Liveness has no dependencies to check - succeeding is the signal."""
        return None
