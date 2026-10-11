import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog

from app.modules.identity.application.permissions import IdentityPermission
from app.modules.identity.domain.user import Role, User, validate_password
from app.modules.identity.ports.password_hasher import PasswordHasher  # noqa: TC001
from app.modules.identity.ports.unit_of_work import IdentityUnitOfWork
from app.shared_kernel.cqrs import AuthorisedCommandHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor
    from app.shared_kernel.authorization import AuthorizationPort

logger = structlog.get_logger()


@dataclass(kw_only=True)
class CreateUserCommand:
    """Request to create an account with an initial password."""

    username: str
    display_name: str
    password: str
    role: Role = Role.MEMBER

    def __repr__(self) -> str:
        """Keep the password out of logs and tracebacks."""
        return f"CreateUserCommand(username={self.username!r})"


class CreateUser(
    AuthorisedCommandHandler[
        IdentityUnitOfWork, CreateUserCommand, User, IdentityPermission
    ]
):
    """Create an account that must change its initial password at first sign-in."""

    required_permission = IdentityPermission.CREATE_USER

    def __init__(
        self,
        uow: IdentityUnitOfWork,
        authorization: AuthorizationPort,
        hasher: PasswordHasher,
    ) -> None:
        super().__init__(uow, authorization)
        self._hasher = hasher

    async def _handle(self, command: CreateUserCommand, actor: Actor) -> User:
        """Create and store the account.

        Raises:
            ForbiddenError: If `actor` lacks `identity:user:create`.
            InvalidUserError: If the username or display name is unusable.
            InvalidPasswordError: If the password breaks the rules.
            UsernameTakenError: If the username is in use.
        """
        validate_password(command.password, command.username)
        user = User.create(
            username=command.username,
            display_name=command.display_name,
            password_hash=await asyncio.to_thread(self._hasher.hash, command.password),
            now=datetime.now(UTC),
            role=command.role,
            password_expired=True,
        )
        async with self._uow as repos:
            await repos.users.add(user)
            await self._uow.commit()
        logger.info("user created", user_id=user.id, created_by=actor.id)
        return user
