import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.identity.application.client_device import ClientDevice
from app.modules.identity.application.session_start import SignedInResult, start_session
from app.modules.identity.application.sign_in_throttle import (
    Reservation,
    SignInThrottle,
    ip_key,
    username_key,
)
from app.modules.identity.domain.errors import (
    AccountDisabledError,
    InvalidCredentialsError,
)
from app.modules.identity.ports.authenticator import Authenticator, PasswordCredentials
from app.modules.identity.ports.password_hasher import PasswordHasher  # noqa: TC001
from app.modules.identity.ports.session_token_generator import SessionTokenGenerator  # noqa: TC001
from app.modules.identity.ports.unit_of_work import IdentityUnitOfWork
from app.shared_kernel.access import Access, Public
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()

_GENERIC_MESSAGE = "Incorrect username or password."
# Enough of the username key to correlate log lines without naming the account.
_LOG_HASH_LENGTH = 12


@dataclass(kw_only=True)
class SignInCommand:
    """Request to sign in with a username and password."""

    username: str
    password: str
    client_ip: str | None = None
    device: ClientDevice | None = None

    def __repr__(self) -> str:
        """Keep the password out of logs and tracebacks."""
        return f"SignInCommand(username={self.username!r})"


class SignIn(CommandHandler[IdentityUnitOfWork, SignInCommand, SignedInResult]):
    """Check credentials and start a session."""

    access: ClassVar[Access] = Public()

    def __init__(
        self,
        uow: IdentityUnitOfWork,
        guard: AccessGuard,
        authenticator: Authenticator,
        tokens: SessionTokenGenerator,
        hasher: PasswordHasher,
        throttle: SignInThrottle,
        *,
        decoy_hash: str,
        session_ttl: timedelta,
    ) -> None:
        super().__init__(uow, guard)
        self._authenticator = authenticator
        self._tokens = tokens
        self._hasher = hasher
        self._throttle = throttle
        self._decoy_hash = decoy_hash
        self._ttl = session_ttl

    async def _refund(self, reservation: Reservation) -> None:
        """Give the attempt back: a disabled account's correct check is no failure."""
        async with self._uow as repos:
            await self._throttle.settle_refund(repos.attempts, reservation)
            await self._uow.commit()

    async def _handle(self, command: SignInCommand, actor: Actor) -> SignedInResult:
        """Return the signed-in user and the new session token.

        Attempts are counted per username and per client address, whether or
        not the account exists, before the password is checked; one past a
        limit is refused unchecked. A correct password clears the username
        counter and refunds the address's.

        Raises:
            InvalidCredentialsError: For an unknown user or wrong password.
            AccountDisabledError: If the credentials are right but the account
                is disabled (not counted as a failure).
            SignInThrottledError: If the username or address is locked.
        """
        now = datetime.now(UTC)
        name_key = username_key(command.username)
        keys = [name_key]
        if command.client_ip:
            keys.append(ip_key(command.client_ip))
        log_fields = {
            "client_ip": command.client_ip,
            "username_hash": name_key.digest[:_LOG_HASH_LENGTH],
        }
        # Count the attempt before checking the password, so parallel guesses
        # cannot all pass a check made before any of them is recorded.
        async with self._uow as repos:
            reservation = await self._throttle.reserve(repos.attempts, keys, now)
            await self._uow.commit()
        if reservation.locked_until is not None:
            # Spend one hash's time so a lock is not faster than a real check.
            await asyncio.to_thread(self._hasher.verify, "decoy", self._decoy_hash)
            logger.warning("sign_in_throttled", **log_fields)
            raise self._throttle.throttled(reservation.locked_until, now)

        try:
            identity = await self._authenticator.authenticate(
                PasswordCredentials(
                    username=command.username, password=command.password
                )
            )
        except AccountDisabledError:
            await self._refund(reservation)
            raise
        if identity is None:
            logger.warning("sign_in_failed", **log_fields)
            raise InvalidCredentialsError(_GENERIC_MESSAGE)
        async with self._uow as repos:
            user = await repos.users.get_by_username_for_update(identity.subject)
            if user is None or user.password_hash != identity.credential_hash:
                # Gone or changed since the check: the password no longer applies.
                logger.warning("sign_in_failed", **log_fields)
                raise InvalidCredentialsError(_GENERIC_MESSAGE)
            if user.disabled:
                await self._throttle.settle_refund(repos.attempts, reservation)
                await self._uow.commit()
                raise AccountDisabledError()
            user.record_sign_in(now)
            await repos.users.save(user)
            await self._throttle.settle_success(repos.attempts, reservation)
            # Sign-in is the only recurring writer here, so it also sweeps old rows.
            await repos.sessions.delete_expired(now)
            started = await start_session(
                repos,
                self._tokens,
                user,
                self._ttl,
                client_ip=command.client_ip,
                device=command.device,
            )
            await self._uow.commit()
        logger.info("signed in", user_id=user.id, session_id=started.session_id)
        return SignedInResult(
            user=user, token=started.token, session_id=started.session_id
        )
