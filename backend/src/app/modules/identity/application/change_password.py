import asyncio
from dataclasses import dataclass
from datetime import timedelta  # noqa: TC003
from typing import TYPE_CHECKING

import structlog

from app.modules.identity.application.session_start import SignedInResult, start_session
from app.modules.identity.domain.errors import (
    CurrentPasswordIncorrectError,
    UserNotFoundError,
)
from app.modules.identity.domain.user import validate_password
from app.modules.identity.ports.password_hasher import PasswordHasher  # noqa: TC001
from app.modules.identity.ports.session_token_generator import (  # noqa: TC001
    SessionTokenGenerator,
)
from app.modules.identity.ports.unit_of_work import IdentityUnitOfWork
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class ChangePasswordCommand:
    """Request to replace the acting user's own password."""

    current_password: str
    new_password: str

    def __repr__(self) -> str:
        """Keep the passwords out of logs and tracebacks."""
        return "ChangePasswordCommand()"


class ChangePassword(
    CommandHandler[IdentityUnitOfWork, ChangePasswordCommand, SignedInResult]
):
    """Change the acting user's password and replace every session with one new one."""

    def __init__(
        self,
        uow: IdentityUnitOfWork,
        hasher: PasswordHasher,
        tokens: SessionTokenGenerator,
        *,
        session_ttl: timedelta,
    ) -> None:
        super().__init__(uow)
        self._hasher = hasher
        self._tokens = tokens
        self._ttl = session_ttl

    async def handle(
        self, command: ChangePasswordCommand, actor: Actor
    ) -> SignedInResult:
        """Change the password, returning the user and the replacement session token.

        Raises:
            UserNotFoundError: If the acting account no longer exists.
            CurrentPasswordIncorrectError: If the current password is wrong.
            InvalidPasswordError: If the new password breaks the rules.
        """
        async with self._uow as repos:
            user = await repos.users.get_for_update(actor.id)
            if user is None:
                raise UserNotFoundError("That account does not exist.")
            if not await asyncio.to_thread(
                self._hasher.verify, command.current_password, user.password_hash
            ):
                raise CurrentPasswordIncorrectError(
                    "The current password is incorrect."
                )
            validate_password(command.new_password, user.username)
            user.change_password(
                await asyncio.to_thread(self._hasher.hash, command.new_password)
            )
            await repos.users.save(user)
            await repos.sessions.delete_for_user(user.id)
            token = await start_session(repos, self._tokens, user, self._ttl)
            await self._uow.commit()
        logger.info("password changed", user_id=user.id)
        return SignedInResult(user=user, token=token)
