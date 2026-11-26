from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar

from app.modules.identity.application.permissions import IdentityPermission
from app.modules.identity.application.sign_in_throttle import username_key
from app.modules.identity.application.user_listing import UserListing
from app.modules.identity.ports.unit_of_work import IdentityRepos
from app.shared_kernel.access import Access, Requires
from app.shared_kernel.cqrs import QueryHandler
from app.shared_kernel.paging import Page, PagedQuery, page_rows, timestamp_value

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor


class UserSort(StrEnum):
    """What the accounts can be sorted by: fields of the response."""

    USERNAME = "username"
    DISPLAY_NAME = "display_name"
    ROLE = "role"
    LAST_LOGIN_AT = "last_login_at"
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"


@dataclass(kw_only=True)
class ListUsersQuery(PagedQuery[UserSort]):
    """Request to list the accounts, by username unless told."""


class ListUsers(QueryHandler[IdentityRepos, ListUsersQuery, Page[UserListing]]):
    """List every account with its sign-in lock state, for administrators."""

    access: ClassVar[Access] = Requires(IdentityPermission.LIST_USERS)

    async def _handle(self, query: ListUsersQuery, actor: Actor) -> Page[UserListing]:
        """Return a page of users, each with when its sign-in lock ends (if locked).

        Raises:
            ForbiddenError: If `actor` lacks `identity:user:list`.
        """
        users = await self._repos.users.list_all()
        locked = await self._repos.attempts.locked_keys(
            [username_key(user.username) for user in users], now=datetime.now(UTC)
        )
        listings = [
            UserListing(user=user, locked_until=locked.get(username_key(user.username)))
            for user in users
        ]
        return page_rows(
            listings,
            query.page_request(UserSort.USERNAME),
            id_of=lambda item: item.user.id,
            values={
                UserSort.USERNAME: lambda item: item.user.username.lower(),
                UserSort.DISPLAY_NAME: lambda item: item.user.display_name.lower(),
                UserSort.ROLE: lambda item: str(item.user.role),
                UserSort.LAST_LOGIN_AT: lambda item: (
                    None
                    if item.user.last_login_at is None
                    else timestamp_value(item.user.last_login_at)
                ),
                UserSort.CREATED_AT: lambda item: timestamp_value(item.user.created_at),
                UserSort.UPDATED_AT: lambda item: timestamp_value(item.user.updated_at),
            },
        )
