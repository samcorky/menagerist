from typing import TYPE_CHECKING

from app.shared_kernel.access_scope import AccessScope
from app.shared_kernel.errors import ForbiddenError, NotFoundError

if TYPE_CHECKING:
    import uuid

    from app.shared_kernel.actor import Actor


class OwnerAccessPolicy:
    """Stage 1 policy: people see and change only what they own.

    Administrators get no special view of other people's content. Content with
    no owner is visible to nobody. The system actor sees everything.
    """

    def scope_for(self, actor: Actor) -> AccessScope:
        """Return everything for the system actor, else the actor's own content."""
        if actor.is_system:
            return AccessScope.everyone()
        return AccessScope.of(actor.id)

    def assert_can_view(self, actor: Actor, owner_id: uuid.UUID | None) -> None:
        """Raise `NotFoundError` unless the content is the actor's own."""
        if actor.is_system or owner_id == actor.id:
            return
        raise NotFoundError("Not found.")

    def assert_can_modify(self, actor: Actor, owner_id: uuid.UUID | None) -> None:
        """Raise `NotFoundError` unless the content is the actor's own."""
        self.assert_can_view(actor, owner_id)

    def assert_can_delete(self, actor: Actor, owner_id: uuid.UUID | None) -> None:
        """Raise `NotFoundError` unless the content is the actor's own."""
        self.assert_can_view(actor, owner_id)

    def require_admin(self, actor: Actor) -> None:
        """Raise `ForbiddenError` unless the actor is an administrator."""
        if not (actor.is_admin or actor.is_system):
            raise ForbiddenError("Administrator access is required.")
