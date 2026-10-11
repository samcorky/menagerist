from typing import TYPE_CHECKING

from app.modules.identity.domain.user import Role
from app.shared_kernel.errors import ForbiddenError

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor


def require_admin(actor: Actor) -> None:
    """Raise `ForbiddenError` unless `actor` is an administrator or the system."""
    if Role.ADMIN.value not in actor.roles and not actor.is_system:
        raise ForbiddenError("Administrator access is required.")
