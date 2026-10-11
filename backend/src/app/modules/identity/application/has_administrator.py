from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.modules.identity.ports.unit_of_work import IdentityRepos
from app.shared_kernel.cqrs import QueryHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True)
class HasAdministratorQuery:
    """Request to learn whether any enabled administrator exists."""


class HasAdministrator(QueryHandler[IdentityRepos, HasAdministratorQuery, bool]):
    """Whether at least one enabled administrator exists."""

    async def handle(self, query: HasAdministratorQuery, actor: Actor) -> bool:
        """Return `True` if an enabled administrator exists."""
        return await self._repos.users.count_admins() > 0
