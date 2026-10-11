import asyncio
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from app.modules.identity.application.admin_only import require_admin
from app.modules.identity.domain.errors import UserNotFoundError
from app.modules.identity.domain.user import validate_password
from app.modules.identity.ports.password_hasher import PasswordHasher  # noqa: TC001
from app.modules.identity.ports.unit_of_work import IdentityUnitOfWork
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class ResetPasswordCommand:
    """Request to give an account a new initial password."""

    user_id: uuid.UUID
    password: str

    def __repr__(self) -> str:
        """Keep the password out of logs and tracebacks."""
        return f"ResetPasswordCommand(user_id={self.user_id!r})"


class ResetPassword(CommandHandler[IdentityUnitOfWork, ResetPasswordCommand, None]):
    """Set a new initial password, end the user's sessions and require a change."""

    def __init__(self, uow: IdentityUnitOfWork, hasher: PasswordHasher) -> None:
        super().__init__(uow)
        self._hasher = hasher

    async def handle(self, command: ResetPasswordCommand, actor: Actor) -> None:
        """Replace the password under a row lock.

        Raises:
            ForbiddenError: If `actor` is not an administrator.
            UserNotFoundError: If the account does not exist.
            InvalidPasswordError: If the password breaks the rules.
        """
        require_admin(actor)
        async with self._uow as repos:
            user = await repos.users.get_for_update(command.user_id)
            if user is None:
                raise UserNotFoundError("That account does not exist.")
            validate_password(command.password, user.username)
            user.change_password(
                await asyncio.to_thread(self._hasher.hash, command.password),
                expired=True,
            )
            await repos.users.save(user)
            await repos.sessions.delete_for_user(user.id)
            await self._uow.commit()
        logger.info("password reset", user_id=user.id, reset_by=actor.id)
