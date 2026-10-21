import asyncio
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from app.modules.identity.application.permissions import IdentityPermission
from app.modules.identity.application.sign_in_throttle import user_id_key, username_key
from app.modules.identity.domain.errors import UserNotFoundError
from app.modules.identity.domain.user import validate_password
from app.modules.identity.ports.password_hasher import PasswordHasher  # noqa: TC001
from app.modules.identity.ports.unit_of_work import IdentityUnitOfWork
from app.shared_kernel.cqrs import AuthorisedCommandHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor
    from app.shared_kernel.authorisation import AuthorisationPort

logger = structlog.get_logger()


@dataclass(kw_only=True)
class ResetPasswordCommand:
    """Request to give an account a new initial password."""

    user_id: uuid.UUID
    password: str

    def __repr__(self) -> str:
        """Keep the password out of logs and tracebacks."""
        return f"ResetPasswordCommand(user_id={self.user_id!r})"


class ResetPassword(
    AuthorisedCommandHandler[
        IdentityUnitOfWork, ResetPasswordCommand, None, IdentityPermission
    ]
):
    """Set a new initial password, end the user's sessions and require a change."""

    required_permission = IdentityPermission.RESET_USER_PASSWORD

    def __init__(
        self,
        uow: IdentityUnitOfWork,
        authorisation: AuthorisationPort,
        hasher: PasswordHasher,
    ) -> None:
        super().__init__(uow, authorisation)
        self._hasher = hasher

    async def _handle(self, command: ResetPasswordCommand, actor: Actor) -> None:
        """Replace the password under a row lock, lifting its sign-in locks.

        Raises:
            ForbiddenError: If `actor` lacks `identity:user:reset_password`.
            UserNotFoundError: If the account does not exist.
            InvalidPasswordError: If the password breaks the rules.
        """
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
            await repos.attempts.clear(username_key(user.username))
            await repos.attempts.clear(user_id_key(user.id))
            ended = await repos.sessions.delete_for_user(user.id)
            await self._uow.commit()
        logger.info("sessions ended", user_id=user.id, count=ended)
        logger.info("password reset", user_id=user.id, reset_by=actor.id)
