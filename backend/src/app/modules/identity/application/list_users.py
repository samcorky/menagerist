from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.modules.identity.application.permissions import IdentityPermission
from app.modules.identity.application.sign_in_throttle import username_key
from app.modules.identity.application.user_listing import UserListing
from app.modules.identity.ports.unit_of_work import IdentityRepos
from app.shared_kernel.cqrs import AuthorisedQueryHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True)
class ListUsersQuery:
    """Request to list every account."""


class ListUsers(
    AuthorisedQueryHandler[
        IdentityRepos, ListUsersQuery, list[UserListing], IdentityPermission
    ]
):
    """List every account with its sign-in lock state, for administrators."""

    required_permission = IdentityPermission.LIST_USERS

    async def _handle(self, query: ListUsersQuery, actor: Actor) -> list[UserListing]:
        """Return all users, each with when its sign-in lock ends (if locked).

        Raises:
            ForbiddenError: If `actor` lacks `identity:user:list`.
        """
        users = await self._repos.users.list_all()
        locked = await self._repos.attempts.locked_keys(
            [username_key(user.username) for user in users], now=datetime.now(UTC)
        )
        return [
            UserListing(user=user, locked_until=locked.get(username_key(user.username)))
            for user in users
        ]
