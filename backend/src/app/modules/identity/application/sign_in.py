from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import structlog

from app.modules.identity.application.session_start import SignedInResult, start_session
from app.modules.identity.domain.errors import InvalidCredentialsError
from app.modules.identity.ports.authenticator import Authenticator, PasswordCredentials
from app.modules.identity.ports.session_token_generator import (  # noqa: TC001
    SessionTokenGenerator,
)
from app.modules.identity.ports.unit_of_work import IdentityUnitOfWork
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()

_GENERIC_MESSAGE = "Incorrect username or password."


@dataclass(kw_only=True)
class SignInCommand:
    """Request to sign in with a username and password."""

    username: str
    password: str

    def __repr__(self) -> str:
        """Keep the password out of logs and tracebacks."""
        return f"SignInCommand(username={self.username!r})"


class SignIn(CommandHandler[IdentityUnitOfWork, SignInCommand, SignedInResult]):
    """Check credentials and start a session."""

    def __init__(
        self,
        uow: IdentityUnitOfWork,
        authenticator: Authenticator,
        tokens: SessionTokenGenerator,
        *,
        session_ttl: timedelta,
    ) -> None:
        super().__init__(uow)
        self._authenticator = authenticator
        self._tokens = tokens
        self._ttl = session_ttl

    async def handle(self, command: SignInCommand, actor: Actor) -> SignedInResult:
        """Return the signed-in user and the new session token.

        Raises:
            InvalidCredentialsError: For an unknown user, wrong password or
                disabled account alike.
            SignInThrottledError: If the account is locked after repeated failures.
        """
        identity = await self._authenticator.authenticate(
            PasswordCredentials(username=command.username, password=command.password)
        )
        if identity is None:
            raise InvalidCredentialsError(_GENERIC_MESSAGE)
        async with self._uow as repos:
            user = await repos.users.get_by_username(identity.subject)
            if user is None or user.disabled:
                raise InvalidCredentialsError(_GENERIC_MESSAGE)
            # Sign-in is the only recurring writer here, so it also sweeps old rows.
            await repos.sessions.delete_expired(datetime.now(UTC))
            token = await start_session(repos, self._tokens, user, self._ttl)
            await self._uow.commit()
        logger.info("user signed in", user_id=user.id)
        return SignedInResult(user=user, token=token)
