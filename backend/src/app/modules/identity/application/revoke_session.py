import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.identity.application.permissions import IdentityPermission
from app.modules.identity.domain.errors import CurrentSessionError, SessionNotFoundError
from app.modules.identity.ports.unit_of_work import IdentityUnitOfWork
from app.shared_kernel.access import Access, Requires
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True, frozen=True)
class RevokeSessionCommand:
    """Request by an administrator to end any active session."""

    session_id: uuid.UUID
    current_session_id: uuid.UUID


class RevokeSession(CommandHandler[IdentityUnitOfWork, RevokeSessionCommand, None]):
    """End any active session by ID, for administrators.

    Refused with `CurrentSessionError` if the target is the actor's own current session,
    and with `SessionNotFoundError` if the session does not exist.
    """

    access: ClassVar[Access] = Requires(IdentityPermission.REVOKE_SESSION)

    def __init__(
        self,
        uow: IdentityUnitOfWork,
        guard: AccessGuard,
    ) -> None:
        super().__init__(uow, guard)

    async def _handle(self, command: RevokeSessionCommand, actor: Actor) -> None:
        """Revoke the requested session if not the actor's current session.

        Raises:
            ForbiddenError: If `actor` lacks `identity:session:revoke`.
            CurrentSessionError: If target is `command.current_session_id`.
            SessionNotFoundError: If the session does not exist.
        """
        if command.session_id == command.current_session_id:
            raise CurrentSessionError("Cannot revoke the current session.")

        async with self._uow as repos:
            session = await repos.sessions.get(command.session_id)
            if session is None:
                raise SessionNotFoundError(f"Session {command.session_id} not found.")
            await repos.sessions.delete(session.id)
            await self._uow.commit()

        logger.info(
            "session revoked",
            user_id=session.user_id,
            session_id=command.session_id,
            revoked_by=actor.id,
        )
