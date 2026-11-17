import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from app.modules.identity.application._picture_writes import clear_picture
from app.modules.identity.application.permissions import IdentityPermission
from app.modules.identity.domain.user import User
from app.modules.identity.ports.unit_of_work import IdentityUnitOfWork
from app.shared_kernel.access import Access, Requires
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.modules.identity.ports.avatar_storage import AvatarStorage
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True)
class ClearUserAvatarCommand:
    """Request to remove someone's picture."""

    user_id: uuid.UUID


class ClearUserAvatar(CommandHandler[IdentityUnitOfWork, ClearUserAvatarCommand, User]):
    """Remove another account's picture, for administrators."""

    access: ClassVar[Access] = Requires(IdentityPermission.UPDATE_USER)

    def __init__(
        self, uow: IdentityUnitOfWork, guard: AccessGuard, storage: AvatarStorage
    ) -> None:
        super().__init__(uow, guard)
        self._storage = storage

    async def _handle(self, command: ClearUserAvatarCommand, actor: Actor) -> User:
        """Clear the account's picture and remove its files.

        Raises:
            ForbiddenError: If `actor` lacks `identity:user:update`.
            UserNotFoundError: If the account does not exist.
        """
        return await clear_picture(self._uow, self._storage, user_id=command.user_id)
