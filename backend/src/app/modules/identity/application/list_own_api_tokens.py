from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar

from app.modules.identity.application.api_token_issue import utc_now
from app.modules.identity.domain.api_token import ApiToken
from app.modules.identity.ports.unit_of_work import IdentityRepos
from app.shared_kernel.access import Access, OwnAccount
from app.shared_kernel.cqrs import QueryHandler
from app.shared_kernel.paging import (
    Page,
    PagedQuery,
    SortOrder,
    page_rows,
    timestamp_value,
)

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor


class ApiTokenSort(StrEnum):
    """What a person's tokens can be sorted by: fields of the response."""

    NAME = "name"
    CREATED_AT = "created_at"
    EXPIRES_AT = "expires_at"
    LAST_USED_AT = "last_used_at"


@dataclass(kw_only=True)
class ListOwnApiTokensQuery(PagedQuery[ApiTokenSort]):
    """Request to list the calling user's active tokens, newest first unless told."""

    order: SortOrder = SortOrder.DESC


class ListOwnApiTokens(
    QueryHandler[IdentityRepos, ListOwnApiTokensQuery, Page[ApiToken]]
):
    """List the user's unexpired tokens, one page at a time."""

    access: ClassVar[Access] = OwnAccount()

    async def _handle(
        self, query: ListOwnApiTokensQuery, actor: Actor
    ) -> Page[ApiToken]:
        """Return a page of the actor's unexpired tokens."""
        tokens = await self._repos.tokens.list_for_user(actor.id, now=utc_now())
        return page_rows(
            tokens,
            query.page_request(ApiTokenSort.CREATED_AT),
            id_of=lambda token: token.id,
            values={
                ApiTokenSort.NAME: lambda token: token.name.lower(),
                ApiTokenSort.CREATED_AT: lambda t: timestamp_value(t.created_at),
                ApiTokenSort.EXPIRES_AT: lambda t: timestamp_value(t.expires_at),
                ApiTokenSort.LAST_USED_AT: lambda t: (
                    None if t.last_used_at is None else timestamp_value(t.last_used_at)
                ),
            },
        )
