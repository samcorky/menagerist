import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from app.modules.identity.application.permissions import IdentityPermission
from app.modules.identity.application.sign_in_throttle import username_key
from app.modules.identity.domain.errors import UserNotFoundError
from app.modules.identity.ports.unit_of_work import IdentityUnitOfWork
from app.shared_kernel.cqrs import AuthorisedCommandHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class UnlockUserCommand:
    """Request to lift an account's sign-in lockout."""

    user_id: uuid.UUID


class UnlockUser(
    AuthorisedCommandHandler[
        IdentityUnitOfWork, UnlockUserCommand, None, IdentityPermission
    ]
):
    """Clear the failed-attempt counter for an account's username.

    Only the username counter: a locked client address stays locked, and the
    account's disabled flag is untouched. Unlocking an unlocked account is a no-op.
    """

    required_permission = IdentityPermission.UNLOCK_USER

    async def _handle(self, command: UnlockUserCommand, actor: Actor) -> None:
        """Clear the lock.

        Raises:
            ForbiddenError: If `actor` lacks `identity:user:unlock`.
            UserNotFoundError: If the account does not exist.
        """
        async with self._uow as repos:
            user = await repos.users.get(command.user_id)
            if user is None:
                raise UserNotFoundError("That account does not exist.")
            await repos.attempts.clear(username_key(user.username))
            await self._uow.commit()
        logger.info("user unlocked", user_id=user.id, unlocked_by=actor.id)
