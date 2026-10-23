import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.identity.application.client_device import ClientDevice
from app.modules.identity.application.session_start import SignedInResult, start_session
from app.modules.identity.application.sign_in_throttle import (
    SignInThrottle,
    ip_key,
    user_id_key,
)
from app.modules.identity.domain.errors import (
    CurrentPasswordIncorrectError,
    InvalidPasswordError,
    PasswordUnchangedError,
    UserNotFoundError,
)
from app.modules.identity.domain.user import validate_password
from app.modules.identity.ports.password_hasher import PasswordHasher  # noqa: TC001
from app.modules.identity.ports.session_token_generator import (  # noqa: TC001
    SessionTokenGenerator,
)
from app.modules.identity.ports.unit_of_work import IdentityUnitOfWork
from app.shared_kernel.access import Access, OwnAccount
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class ChangePasswordCommand:
    """Request to replace the acting user's own password."""

    current_password: str
    new_password: str
    client_ip: str | None = None
    device: ClientDevice | None = None

    def __repr__(self) -> str:
        """Keep the passwords out of logs and tracebacks."""
        return "ChangePasswordCommand()"


class ChangePassword(
    CommandHandler[IdentityUnitOfWork, ChangePasswordCommand, SignedInResult]
):
    """Change the acting user's password and replace every session with one new one."""

    access: ClassVar[Access] = OwnAccount()

    def __init__(
        self,
        uow: IdentityUnitOfWork,
        guard: AccessGuard,
        hasher: PasswordHasher,
        tokens: SessionTokenGenerator,
        throttle: SignInThrottle,
        *,
        session_ttl: timedelta,
    ) -> None:
        super().__init__(uow, guard)
        self._hasher = hasher
        self._throttle = throttle
        self._tokens = tokens
        self._ttl = session_ttl

    @staticmethod
    def _refusal(
        command: ChangePasswordCommand, username: str
    ) -> InvalidPasswordError | PasswordUnchangedError | None:
        """Return why the new password is refused, or `None` if it is fine."""
        try:
            validate_password(command.new_password, username)
        except InvalidPasswordError as error:
            return error
        if command.new_password == command.current_password:
            return PasswordUnchangedError(
                "The new password must differ from the current one."
            )
        return None

    async def _handle(
        self, command: ChangePasswordCommand, actor: Actor
    ) -> SignedInResult:
        """Change the password, returning the user and the replacement session token.

        Raises:
            UserNotFoundError: If the acting account no longer exists.
            CurrentPasswordIncorrectError: If the current password is wrong.
            SignInThrottledError: If this user or address has failed too often.
            InvalidPasswordError: If the new password breaks the rules.
            PasswordUnchangedError: If the new password is the current one.
        """
        now = datetime.now(UTC)
        keys = [user_id_key(actor.id)]
        if command.client_ip:
            keys.append(ip_key(command.client_ip))
        # Count the attempt before checking the password (see `SignIn`).
        async with self._uow as repos:
            reservation = await self._throttle.reserve(repos.attempts, keys, now)
            await self._uow.commit()
        if reservation.locked_until is not None:
            raise self._throttle.throttled(reservation.locked_until, now)
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
            # The current password verified, so a refused new one is no failure.
            refusal = self._refusal(command, user.username)
            if refusal is not None:
                await self._throttle.settle_refund(repos.attempts, reservation)
                await self._uow.commit()
                raise refusal
            await self._throttle.settle_success(repos.attempts, reservation)
            user.change_password(
                await asyncio.to_thread(self._hasher.hash, command.new_password)
            )
            await repos.users.save(user)
            ended = await repos.sessions.delete_for_user(user.id)
            tokens_ended = await repos.tokens.delete_for_user(user.id)
            started = await start_session(
                repos,
                self._tokens,
                user,
                self._ttl,
                client_ip=command.client_ip,
                device=command.device,
            )
            await self._uow.commit()
        logger.info("sessions ended", user_id=user.id, count=ended)
        logger.info("api tokens ended", user_id=user.id, count=tokens_ended)
        logger.info("password changed", user_id=user.id, session_id=started.session_id)
        return SignedInResult(
            user=user, token=started.token, session_id=started.session_id
        )
