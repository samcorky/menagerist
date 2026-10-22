from typing import TYPE_CHECKING

from app.entrypoints.api.shared.permissions import ALL_PERMISSIONS, Permission, expand
from app.modules.backup.application.permissions import BackupPermission
from app.modules.collections.application.permissions import CollectionPermission
from app.modules.examples.application.permissions import ExamplePermission
from app.modules.graph.application.permissions import GraphPermission
from app.modules.media.application.permissions import MediaPermission
from app.modules.presets.application.permissions import PresetPermission
from app.shared_kernel.errors import ForbiddenError

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor
    from app.shared_kernel.authorisation import AuthorisationPort

# Permissions for owned content and the shared catalogue.
CONTENT_PERMISSIONS: frozenset[Permission] = frozenset(
    {
        GraphPermission.ITEM_READ,
        GraphPermission.ITEM_WRITE,
        GraphPermission.TYPE_READ,
        GraphPermission.TYPE_WRITE,
        MediaPermission.ITEM_READ,
        MediaPermission.ITEM_WRITE,
        CollectionPermission.COLLECTION_READ,
        CollectionPermission.COLLECTION_WRITE,
        PresetPermission.PRESET_READ,
        PresetPermission.PRESET_WRITE,
        ExamplePermission.PACK_READ,
        ExamplePermission.PACK_INSTALL,
        BackupPermission.EXPORT_OWN_DATA,
        BackupPermission.IMPORT_OWN_DATA,
    }
)

# Granted to every signed-in member.
MEMBER_PERMISSIONS: frozenset[Permission] = CONTENT_PERMISSIONS

# Derived: what only administrators hold.
ADMIN_ONLY_ACTIONS: frozenset[Permission] = ALL_PERMISSIONS - MEMBER_PERMISSIONS


class RoleAuthorisationAdapter:
    """Role-based `AuthorisationPort` over an actor's effective permissions.

    The system actor and administrators hold every permission; members hold
    `MEMBER_PERMISSIONS`. Grants expand through the implication catalogue, and a
    permission outside the catalogue is denied to everyone.
    """

    def __init__(
        self,
        member_permissions: frozenset[Permission] = MEMBER_PERMISSIONS,
    ) -> None:
        self._member_permissions = member_permissions

    def effective_permissions(self, actor: Actor) -> frozenset[Permission]:
        """Return every permission `actor` holds, implications included."""
        granted = (
            ALL_PERMISSIONS
            if actor.is_admin or actor.is_system
            else self._member_permissions
        )
        return expand(granted)

    async def check(self, actor: Actor, action: str) -> None:
        """Raise `ForbiddenError` unless `action` is in the actor's permissions."""
        if action not in self.effective_permissions(actor):
            raise ForbiddenError("You do not have permission to do that.")


_authorisation_port = RoleAuthorisationAdapter()


def get_role_authorisation() -> RoleAuthorisationAdapter:
    """Return the process-wide role-based authorisation adapter."""
    return _authorisation_port


def get_authorisation_port() -> AuthorisationPort:
    """Return the process-wide `AuthorisationPort` adapter."""
    return _authorisation_port
