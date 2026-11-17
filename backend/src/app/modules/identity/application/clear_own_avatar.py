from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from app.modules.identity.application._picture_writes import clear_picture
from app.modules.identity.domain.user import User
from app.modules.identity.ports.unit_of_work import IdentityUnitOfWork
from app.shared_kernel.access import Access, OwnAccount
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.modules.identity.ports.avatar_storage import AvatarStorage
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True)
class ClearOwnAvatarCommand:
    """Request to go back to the initials default (Use initials)."""


class ClearOwnAvatar(CommandHandler[IdentityUnitOfWork, ClearOwnAvatarCommand, User]):
    """Remove the acting person's picture."""

    access: ClassVar[Access] = OwnAccount()

    def __init__(
        self, uow: IdentityUnitOfWork, guard: AccessGuard, storage: AvatarStorage
    ) -> None:
        super().__init__(uow, guard)
        self._storage = storage

    async def _handle(self, command: ClearOwnAvatarCommand, actor: Actor) -> User:
        """Clear the picture and remove its files.

        Raises:
            UserNotFoundError: If the acting account no longer exists.
        """
        return await clear_picture(self._uow, self._storage, user_id=actor.id)
