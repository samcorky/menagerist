from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from app.modules.identity.ports.unit_of_work import IdentityRepos
from app.shared_kernel.access import Access, Public
from app.shared_kernel.guarded import GuardedQueryHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True)
class HasAdministratorQuery:
    """Request to learn whether any enabled administrator exists."""


class HasAdministrator(GuardedQueryHandler[IdentityRepos, HasAdministratorQuery, bool]):
    """Whether at least one enabled administrator exists."""

    access: ClassVar[Access] = Public()

    async def _handle(self, query: HasAdministratorQuery, actor: Actor) -> bool:
        """Return `True` if an enabled administrator exists."""
        return await self._repos.users.count_admins() > 0
