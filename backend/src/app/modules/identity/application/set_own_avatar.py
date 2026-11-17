from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from app.modules.identity.application._picture_writes import replace_picture
from app.modules.identity.domain.avatar import (
    MAX_AVATAR_BYTES,
    AvatarSource,
    CropSquare,
)
from app.modules.identity.domain.errors import InvalidAvatarError
from app.modules.identity.domain.user import User
from app.modules.identity.ports.unit_of_work import IdentityUnitOfWork
from app.shared_kernel.access import Access, OwnAccount
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.modules.identity.ports.avatar_image_processor import AvatarImageProcessor
    from app.modules.identity.ports.avatar_storage import AvatarStorage
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True)
class SetOwnAvatarCommand:
    """A file the acting person chose, or a cat their browser drew, as their picture."""

    data: bytes
    source: AvatarSource = AvatarSource.UPLOAD
    crop: CropSquare | None = None


class SetOwnAvatar(CommandHandler[IdentityUnitOfWork, SetOwnAvatarCommand, User]):
    """Make an uploaded file the acting person's picture."""

    access: ClassVar[Access] = OwnAccount()

    def __init__(
        self,
        uow: IdentityUnitOfWork,
        guard: AccessGuard,
        processor: AvatarImageProcessor,
        storage: AvatarStorage,
    ) -> None:
        super().__init__(uow, guard)
        self._processor = processor
        self._storage = storage

    async def _handle(self, command: SetOwnAvatarCommand, actor: Actor) -> User:
        """Check, process and store the file, then show it as the picture.

        Raises:
            InvalidAvatarError: If the file is over 5 MB, claims to be a cat, or
                cannot be used as a picture.
            UserNotFoundError: If the acting account no longer exists.
        """
        if command.source is AvatarSource.CAT:
            raise InvalidAvatarError("Only Random cat can set a cat picture.")
        if len(command.data) > MAX_AVATAR_BYTES:
            raise InvalidAvatarError("A picture must be 5 MB or smaller.")
        processed = await self._processor.process(command.data, crop=command.crop)
        return await replace_picture(
            self._uow,
            self._storage,
            user_id=actor.id,
            processed=processed,
            source=command.source,
        )
