from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from app.modules.identity.application._picture_writes import replace_picture
from app.modules.identity.domain.avatar import AvatarSource
from app.modules.identity.domain.errors import (
    CatServiceUnavailableError,
    InvalidAvatarError,
)
from app.modules.identity.domain.user import User
from app.modules.identity.ports.unit_of_work import IdentityUnitOfWork
from app.shared_kernel.access import Access, OwnAccount
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.modules.identity.ports.avatar_image_processor import AvatarImageProcessor
    from app.modules.identity.ports.avatar_storage import AvatarStorage
    from app.modules.identity.ports.cat_picture_source import CatPictureSource
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True)
class SetOwnAvatarFromCatServiceCommand:
    """Request for a new random cat as the acting person's picture."""


class SetOwnAvatarFromCatService(
    CommandHandler[IdentityUnitOfWork, SetOwnAvatarFromCatServiceCommand, User]
):
    """Random cat: fetch a cat server-side and keep it like an upload."""

    access: ClassVar[Access] = OwnAccount()

    def __init__(
        self,
        uow: IdentityUnitOfWork,
        guard: AccessGuard,
        cats: CatPictureSource,
        processor: AvatarImageProcessor,
        storage: AvatarStorage,
    ) -> None:
        super().__init__(uow, guard)
        self._cats = cats
        self._processor = processor
        self._storage = storage

    async def _handle(
        self, command: SetOwnAvatarFromCatServiceCommand, actor: Actor
    ) -> User:
        """Fetch one cat, process it like an upload and show it as the picture.

        Raises:
            CatServiceUnavailableError: If the service is off, unreachable, or sent
                something that cannot be used as a picture.
            UserNotFoundError: If the acting account no longer exists.
        """
        data = await self._cats.fetch()
        try:
            processed = await self._processor.process(data, crop=None)
        except InvalidAvatarError as error:
            # A reply that is not a usable picture is the service failing, so the
            # browser falls back to drawing a cat, as it does when it is unreachable.
            raise CatServiceUnavailableError(
                "The cat service sent something that is not a picture."
            ) from error
        return await replace_picture(
            self._uow,
            self._storage,
            user_id=actor.id,
            processed=processed,
            source=AvatarSource.CAT,
        )
