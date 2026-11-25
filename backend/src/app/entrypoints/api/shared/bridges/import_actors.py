"""Who a queued import runs as: its owner's account as it is now.

Implements transfer's `ImportActors` with identity's `GetAccountRole`, so transfer
never reads accounts.
"""

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.modules.identity.adapters.persistence.unit_of_work import build_identity_repos
from app.modules.identity.application.get_account_role import (
    GetAccountRole,
    GetAccountRoleQuery,
)
from app.shared_kernel.actor import SYSTEM_ACTOR, Actor

if TYPE_CHECKING:
    import uuid
    from collections.abc import AsyncIterator, Callable
    from contextlib import AbstractAsyncContextManager

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.modules.identity.ports.unit_of_work import IdentityRepos


class IdentityImportActors:
    """`ImportActors` over identity's accounts."""

    def __init__(
        self, repos: Callable[[], AbstractAsyncContextManager[IdentityRepos]]
    ) -> None:
        """Initialise with a way to open identity's repositories for each lookup."""
        self._repos = repos

    async def actor_for(
        self, owner_id: uuid.UUID, grants: frozenset[str] | None
    ) -> Actor | None:
        """Return the owner with their current role, capped by `grants`."""
        async with self._repos() as repos:
            role = await GetAccountRole(repos, get_access_guard()).handle(
                GetAccountRoleQuery(user_id=owner_id), SYSTEM_ACTOR
            )
        if role is None:
            return None
        return Actor(id=owner_id, roles=frozenset({role}), grants=grants)


def build_import_actors(
    session_factory: async_sessionmaker[AsyncSession],
) -> IdentityImportActors:
    """`IdentityImportActors` over a fresh Postgres session for each lookup."""

    @asynccontextmanager
    async def opened() -> AsyncIterator[IdentityRepos]:
        async with session_factory() as session:
            yield build_identity_repos(session)

    return IdentityImportActors(opened)
