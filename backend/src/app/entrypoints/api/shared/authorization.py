from typing import TYPE_CHECKING

from app.entrypoints.api.shared.permissions import (
    ALL_PERMISSIONS,
    IMPLIES,
    Permission,
    expand,
)
from app.shared_kernel.errors import ForbiddenError

if TYPE_CHECKING:
    from collections.abc import Mapping

    from app.shared_kernel.actor import Actor

# Granted to every signed-in member; empty today.
MEMBER_PERMISSIONS: frozenset[Permission] = frozenset()

# Derived: what only administrators hold.
ADMIN_ONLY_ACTIONS: frozenset[Permission] = ALL_PERMISSIONS - MEMBER_PERMISSIONS


class RoleAuthorizationAdapter:
    """Role-based `AuthorizationPort` over an actor's effective permissions.

    The system actor and administrators hold every permission; members hold
    `MEMBER_PERMISSIONS`. Grants expand through the implication catalogue, and a
    permission outside the catalogue is denied to everyone.
    """

    def __init__(
        self,
        member_permissions: frozenset[Permission] = MEMBER_PERMISSIONS,
        implies: Mapping[Permission, frozenset[Permission]] = IMPLIES,
    ) -> None:
        self._member_permissions = member_permissions
        self._implies = implies

    def effective_permissions(self, actor: Actor) -> frozenset[Permission]:
        """Return every permission `actor` holds, implications included."""
        granted = (
            ALL_PERMISSIONS
            if actor.is_admin or actor.is_system
            else self._member_permissions
        )
        return expand(granted, self._implies)

    async def check(self, actor: Actor, action: str) -> None:
        """Raise `ForbiddenError` unless `action` is in the actor's permissions."""
        if action not in self.effective_permissions(actor):
            raise ForbiddenError("You do not have permission to do that.")
