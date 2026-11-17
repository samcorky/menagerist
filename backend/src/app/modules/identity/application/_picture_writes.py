from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog

from app.modules.identity.domain.avatar import Avatar, AvatarSource
from app.modules.identity.domain.errors import UserNotFoundError

if TYPE_CHECKING:
    import uuid

    from app.modules.identity.domain.user import User
    from app.modules.identity.ports.avatar_image_processor import ProcessedAvatar
    from app.modules.identity.ports.avatar_storage import AvatarStorage
    from app.modules.identity.ports.unit_of_work import IdentityUnitOfWork

logger = structlog.get_logger()


async def _tidy(
    storage: AvatarStorage, user_id: uuid.UUID, *, keep: str | None
) -> None:
    """Remove files other than `keep`; a file that cannot go yet is only logged.

    The picture has already changed by now, so a stuck file (one being served, on
    Windows) must not turn the change into a failure; the next change removes it.
    """
    try:
        await storage.remove(user_id, keep=keep)
    except OSError:
        logger.warning("old picture files not removed", user_id=user_id, exc_info=True)


async def replace_picture(
    uow: IdentityUnitOfWork,
    storage: AvatarStorage,
    *,
    user_id: uuid.UUID,
    processed: ProcessedAvatar,
    source: AvatarSource,
) -> User:
    """Store `processed`, point the account at it, then drop the older files.

    Everything after the row lock is serialised per account, so two writes at once
    queue rather than deleting each other's files. The files are written before the
    commit, so the new address works as soon as anyone can see it. If the commit
    fails, the files go back to the version the row still names.

    Raises:
        UserNotFoundError: If the account no longer exists.
    """
    async with uow as repos:
        user = await repos.users.get_for_update(user_id)
        if user is None:
            raise UserNotFoundError("That account does not exist.")
        previous = user.avatar.version if user.avatar else None
        await storage.save(user_id, processed)
        try:
            user.set_avatar(
                Avatar(
                    version=processed.version,
                    source=source,
                    updated_at=datetime.now(UTC),
                )
            )
            await repos.users.save(user)
            uow.on_commit(lambda: _tidy(storage, user_id, keep=processed.version))
            await uow.commit()
        except BaseException:
            await _tidy(storage, user_id, keep=previous)
            raise
    logger.info("picture changed", user_id=user_id, source=source.value)
    return user


async def clear_picture(
    uow: IdentityUnitOfWork, storage: AvatarStorage, *, user_id: uuid.UUID
) -> User:
    """Return the account to its initials and remove its files after the commit.

    Raises:
        UserNotFoundError: If the account does not exist.
    """
    async with uow as repos:
        user = await repos.users.get_for_update(user_id)
        if user is None:
            raise UserNotFoundError("That account does not exist.")
        user.clear_avatar()
        await repos.users.save(user)
        uow.on_commit(lambda: _tidy(storage, user_id, keep=None))
        await uow.commit()
    logger.info("picture cleared", user_id=user_id)
    return user
