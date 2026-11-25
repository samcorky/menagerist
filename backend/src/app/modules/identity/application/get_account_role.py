import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from app.modules.identity.ports.unit_of_work import IdentityRepos
from app.shared_kernel.access import Access, System
from app.shared_kernel.cqrs import QueryHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor


@dataclass(frozen=True, kw_only=True)
class GetAccountRoleQuery:
    """The account whose role is wanted."""

    user_id: uuid.UUID


class GetAccountRole(QueryHandler[IdentityRepos, GetAccountRoleQuery, str | None]):
    """An account's role, for work run later on its behalf, such as an import.

    `None` when the account is gone or disabled, so the work does not run.
    """

    access: ClassVar[Access] = System()

    async def _handle(self, query: GetAccountRoleQuery, actor: Actor) -> str | None:
        """Read the account as it is now."""
        user = await self._repos.users.get(query.user_id)
        if user is None or user.disabled:
            return None
        return user.role.value
