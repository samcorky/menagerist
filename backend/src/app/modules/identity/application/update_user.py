import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog

from app.modules.identity.application.permissions import IdentityPermission
from app.modules.identity.application.sign_in_throttle import username_key
from app.modules.identity.application.user_listing import UserListing
from app.modules.identity.domain.errors import LastAdministratorError, UserNotFoundError
from app.modules.identity.domain.user import Role
from app.modules.identity.ports.unit_of_work import IdentityUnitOfWork
from app.shared_kernel.cqrs import AuthorisedCommandHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class UpdateUserCommand:
    """Request to change an account; omitted fields are left as they are."""

    user_id: uuid.UUID
    display_name: str | None = None
    role: Role | None = None
    disabled: bool | None = None


class UpdateUser(
    AuthorisedCommandHandler[
        IdentityUnitOfWork, UpdateUserCommand, UserListing, IdentityPermission
    ]
):
    """Rename, re-role, disable or enable an account."""

    required_permission = IdentityPermission.UPDATE_USER

    async def _handle(self, command: UpdateUserCommand, actor: Actor) -> UserListing:
        """Apply the change under a row lock.

        Raises:
            ForbiddenError: If `actor` lacks `identity:user:update`.
            UserNotFoundError: If the account does not exist.
            InvalidUserError: If the display name is unusable.
            LastAdministratorError: If the change would leave no enabled admin.
        """
        ended = 0
        async with self._uow as repos:
            # Lock order: admin-changes lock first, then the user row.
            await repos.users.lock_admin_changes()
            user = await repos.users.get_for_update(command.user_id)
            if user is None:
                raise UserNotFoundError("That account does not exist.")
            demoting = command.role is not None and command.role is not Role.ADMIN
            is_active_admin = user.role is Role.ADMIN and not user.disabled
            if (
                is_active_admin
                and (command.disabled is True or demoting)
                and await repos.users.count_admins() <= 1
            ):
                raise LastAdministratorError(
                    "There must always be at least one active administrator."
                )
            if command.display_name is not None:
                user.rename(command.display_name)
            if command.role is not None:
                user.set_role(command.role)
            if command.disabled is True:
                user.disable()
                ended = await repos.sessions.delete_for_user(user.id)
            elif command.disabled is False:
                user.enable()
            await repos.users.save(user)
            locked = await repos.attempts.locked_keys(
                [username_key(user.username)], now=datetime.now(UTC)
            )
            await self._uow.commit()
        if ended:
            logger.info("sessions ended", user_id=user.id, count=ended)
        logger.info("user updated", user_id=user.id, updated_by=actor.id)
        return UserListing(
            user=user, locked_until=locked.get(username_key(user.username))
        )
