import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import structlog

from app.modules.identity.application.session_start import start_session
from app.modules.identity.domain.errors import SetupAlreadyDoneError
from app.modules.identity.domain.user import Role, User, validate_password
from app.modules.identity.ports.existing_data_claim import (
    ClaimReport,
    ExistingDataClaim,
)
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
class SetupFirstAdminCommand:
    """Request to create the first administrator."""

    username: str
    display_name: str
    password: str

    def __repr__(self) -> str:
        """Keep the password out of logs and tracebacks."""
        return f"SetupFirstAdminCommand(username={self.username!r})"


@dataclass(kw_only=True, frozen=True)
class SetupFirstAdminResult:
    """The new administrator, their session token and what they took ownership of."""

    user: User
    token: str = field(repr=False)
    claim: ClaimReport


class SetupFirstAdmin(
    CommandHandler[IdentityUnitOfWork, SetupFirstAdminCommand, SetupFirstAdminResult]
):
    """Create the first administrator, sign them in and claim existing content."""

    def __init__(
        self,
        uow: IdentityUnitOfWork,
        hasher: PasswordHasher,
        tokens: SessionTokenGenerator,
        claim: ExistingDataClaim,
        *,
        session_ttl: timedelta,
    ) -> None:
        super().__init__(uow)
        self._hasher = hasher
        self._tokens = tokens
        self._claim = claim
        self._ttl = session_ttl

    async def handle(
        self, command: SetupFirstAdminCommand, actor: Actor
    ) -> SetupFirstAdminResult:
        """Create the administrator when no account exists yet.

        Raises:
            SetupAlreadyDoneError: If any account already exists.
            InvalidUserError: If the username or display name is unusable.
            InvalidPasswordError: If the password breaks the rules.
        """
        async with self._uow as repos:
            # Cheap unlocked check so a finished setup costs no hashing.
            if await repos.users.count() > 0:
                raise SetupAlreadyDoneError("Setup has already been completed.")
        validate_password(command.password, command.username)
        # Hash before taking the setup lock so it is held only briefly.
        user = User.create(
            username=command.username,
            display_name=command.display_name,
            password_hash=await asyncio.to_thread(self._hasher.hash, command.password),
            now=datetime.now(UTC),
            role=Role.ADMIN,
        )
        async with self._uow as repos:
            await repos.users.lock_for_setup()
            if await repos.users.count() > 0:
                raise SetupAlreadyDoneError("Setup has already been completed.")
            await repos.users.add(user)
            token = await start_session(repos, self._tokens, user, self._ttl)
            report = await self._claim.claim(user.id)
            await self._uow.commit()
        logger.info("first administrator created", user_id=user.id)
        return SetupFirstAdminResult(user=user, token=token, claim=report)
