from typing import TYPE_CHECKING, assert_never

from app.entrypoints.api.shared.access_policy import OwnerAccessPolicy
from app.entrypoints.api.shared.authorisation import get_authorisation_port
from app.shared_kernel.access import (
    Content,
    OwnAccount,
    Public,
    Requires,
    Shared,
    System,
)
from app.shared_kernel.errors import ForbiddenError

if TYPE_CHECKING:
    import uuid

    from app.shared_kernel.access import Access
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor
    from app.shared_kernel.authorisation import AuthorisationPort
    from app.shared_kernel.content_filter import ContentFilter


class RoleAccessGuard:
    """Role-based `AccessGuard`: stances over roles, ownership over the policy.

    The anonymous actor is refused before any permission lookup for every
    stance except `Public`, so a later non-empty member grant cannot reach it.
    """

    def __init__(
        self, authorisation: AuthorisationPort, policy: OwnerAccessPolicy
    ) -> None:
        self._authorisation = authorisation
        self._policy = policy

    async def check(self, actor: Actor, access: Access) -> None:
        """Raise `ForbiddenError` unless `actor` satisfies `access`."""
        match access:
            case Public():
                return
            case System():
                allowed = actor.is_system
            case OwnAccount():
                allowed = not actor.is_anonymous and not actor.is_system
            case Shared() | Content():
                allowed = not actor.is_anonymous
            case Requires(permission=permission):
                if not actor.is_anonymous:
                    await self._authorisation.check(actor, permission)
                    return
                allowed = False
            case _:
                assert_never(access)
        if not allowed:
            raise ForbiddenError("You do not have permission to do that.")

    def scope_for(self, actor: Actor) -> ContentFilter:
        """Return the content `actor` may see."""
        return self._policy.scope_for(actor)

    def assert_can_view(self, actor: Actor, owner_id: uuid.UUID | None) -> None:
        """Raise `NotFoundError` unless `actor` may see content owned by `owner_id`."""
        self._policy.assert_can_view(actor, owner_id)

    def assert_can_modify(self, actor: Actor, owner_id: uuid.UUID | None) -> None:
        """Raise `NotFoundError` unless `actor` may change that content."""
        self._policy.assert_can_modify(actor, owner_id)

    def assert_can_delete(self, actor: Actor, owner_id: uuid.UUID | None) -> None:
        """Raise `NotFoundError` unless `actor` may delete that content."""
        self._policy.assert_can_delete(actor, owner_id)


_access_guard = RoleAccessGuard(get_authorisation_port(), OwnerAccessPolicy())


def get_access_guard() -> AccessGuard:
    """Return the process-wide `AccessGuard`."""
    return _access_guard
