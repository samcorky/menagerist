from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from app.modules.identity.application.api_token_issue import held_grants
from app.modules.identity.ports.unit_of_work import IdentityRepos
from app.shared_kernel.access import Access, OwnAccount
from app.shared_kernel.cqrs import QueryHandler

if TYPE_CHECKING:
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor
    from app.shared_kernel.authorisation import AuthorisationPort


@dataclass(kw_only=True, frozen=True)
class ListGrantablePermissionsQuery:
    """Request for the permissions a new token could be given."""


class ListGrantablePermissions(
    QueryHandler[IdentityRepos, ListGrantablePermissionsQuery, list[str]]
):
    """List the grantable permissions the acting user holds, sorted."""

    access: ClassVar[Access] = OwnAccount()

    def __init__(
        self,
        repos: IdentityRepos,
        guard: AccessGuard,
        authorisation: AuthorisationPort,
        *,
        grantable: frozenset[str],
    ) -> None:
        super().__init__(repos, guard)
        self._authorisation = authorisation
        self._grantable = grantable

    async def _handle(
        self, query: ListGrantablePermissionsQuery, actor: Actor
    ) -> list[str]:
        """Return the grantable permissions `actor` holds now."""
        return sorted(await held_grants(self._authorisation, actor, self._grantable))
