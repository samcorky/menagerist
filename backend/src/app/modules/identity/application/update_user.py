import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from app.modules.identity.application.admin_only import require_admin
from app.modules.identity.domain.errors import LastAdministratorError, UserNotFoundError
from app.modules.identity.domain.user import Role, User
from app.modules.identity.ports.unit_of_work import IdentityUnitOfWork
from app.shared_kernel.cqrs import CommandHandler

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


class UpdateUser(CommandHandler[IdentityUnitOfWork, UpdateUserCommand, User]):
    """Rename, re-role, disable or enable an account."""

    async def handle(self, command: UpdateUserCommand, actor: Actor) -> User:
        """Apply the change under a row lock.

        Raises:
            ForbiddenError: If `actor` is not an administrator.
            UserNotFoundError: If the account does not exist.
            InvalidUserError: If the display name is unusable.
            LastAdministratorError: If the change would leave no enabled admin.
        """
        require_admin(actor)
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
            await self._uow.commit()
        if ended:
            logger.info("sessions ended", user_id=user.id, count=ended)
        logger.info("user updated", user_id=user.id, updated_by=actor.id)
        return user
