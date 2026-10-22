from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from app.modules.identity.ports.unit_of_work import IdentityRepos
from app.shared_kernel.access import Access, Public
from app.shared_kernel.guarded import GuardedQueryHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True)
class GetSetupStatusQuery:
    """Request to learn whether first-run setup is still to be done."""


class GetSetupStatus(GuardedQueryHandler[IdentityRepos, GetSetupStatusQuery, bool]):
    """Whether no account exists yet."""

    access: ClassVar[Access] = Public()

    async def _handle(self, query: GetSetupStatusQuery, actor: Actor) -> bool:
        """Return `True` while there are no accounts."""
        return await self._repos.users.count() == 0
