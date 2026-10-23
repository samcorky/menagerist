from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from app.modules.identity.application.api_token_issue import utc_now
from app.modules.identity.domain.api_token import ApiToken
from app.modules.identity.ports.unit_of_work import IdentityRepos
from app.shared_kernel.access import Access, OwnAccount
from app.shared_kernel.cqrs import QueryHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True, frozen=True)
class ListOwnApiTokensQuery:
    """Request to list the calling user's active tokens."""


class ListOwnApiTokens(
    QueryHandler[IdentityRepos, ListOwnApiTokensQuery, list[ApiToken]]
):
    """List the user's unexpired tokens, newest first."""

    access: ClassVar[Access] = OwnAccount()

    async def _handle(
        self, query: ListOwnApiTokensQuery, actor: Actor
    ) -> list[ApiToken]:
        """Return the actor's unexpired tokens."""
        return await self._repos.tokens.list_for_user(actor.id, now=utc_now())
