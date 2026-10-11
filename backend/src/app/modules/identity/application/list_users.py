from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.modules.identity.application.admin_only import require_admin
from app.modules.identity.domain.user import User
from app.modules.identity.ports.unit_of_work import IdentityRepos
from app.shared_kernel.cqrs import QueryHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True)
class ListUsersQuery:
    """Request to list every account."""


class ListUsers(QueryHandler[IdentityRepos, ListUsersQuery, list[User]]):
    """List every account, for administrators."""

    async def handle(self, query: ListUsersQuery, actor: Actor) -> list[User]:
        """Return all users.

        Raises:
            ForbiddenError: If `actor` is not an administrator.
        """
        require_admin(actor)
        return await self._repos.users.list_all()
