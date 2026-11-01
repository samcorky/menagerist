from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.identity.domain.errors import UserNotFoundError
from app.modules.identity.domain.user import User
from app.modules.identity.ports.unit_of_work import IdentityUnitOfWork
from app.shared_kernel.access import Access, OwnAccount
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class SetOwnDisplayNameCommand:
    """Request to change the acting user's own display name."""

    display_name: str


class SetOwnDisplayName(
    CommandHandler[IdentityUnitOfWork, SetOwnDisplayNameCommand, User]
):
    """Rename the acting user; everyone may change their own display name."""

    access: ClassVar[Access] = OwnAccount()

    async def _handle(self, command: SetOwnDisplayNameCommand, actor: Actor) -> User:
        """Rename the acting account under a row lock.

        Raises:
            UserNotFoundError: If the acting account no longer exists.
            InvalidUserError: If the display name is unusable.
        """
        async with self._uow as repos:
            user = await repos.users.get_for_update(actor.id)
            if user is None:
                raise UserNotFoundError("That account does not exist.")
            user.rename(command.display_name)
            await repos.users.save(user)
            await self._uow.commit()
        logger.info("display name changed", user_id=user.id)
        return user
