from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.modules.identity.ports.unit_of_work import IdentityRepos
from app.shared_kernel.cqrs import QueryHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True)
class GetSetupStatusQuery:
    """Request to learn whether first-run setup is still to be done."""


class GetSetupStatus(QueryHandler[IdentityRepos, GetSetupStatusQuery, bool]):
    """Whether no account exists yet."""

    async def handle(self, query: GetSetupStatusQuery, actor: Actor) -> bool:
        """Return `True` while there are no accounts."""
        return await self._repos.users.count() == 0
