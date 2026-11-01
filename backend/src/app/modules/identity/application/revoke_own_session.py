import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.identity.domain.errors import CurrentSessionError, SessionNotFoundError
from app.modules.identity.ports.unit_of_work import IdentityUnitOfWork
from app.shared_kernel.access import Access, OwnAccount
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True, frozen=True)
class RevokeOwnSessionCommand:
    """Request to end one of the calling user's sessions."""

    session_id: uuid.UUID
    current_session_id: uuid.UUID


class RevokeOwnSession(
    CommandHandler[IdentityUnitOfWork, RevokeOwnSessionCommand, None]
):
    """End one of the user's sessions.

    Refused with `CurrentSessionError` if the session is the current one,
    and with `SessionNotFoundError` if unknown or owned by another user.
    """

    access: ClassVar[Access] = OwnAccount()

    async def _handle(self, command: RevokeOwnSessionCommand, actor: Actor) -> None:
        """Revoke the requested session if it belongs to `actor`."""
        if command.session_id == command.current_session_id:
            raise CurrentSessionError("Cannot revoke the current session.")

        async with self._uow as repos:
            session = await repos.sessions.get(command.session_id)
            if session is None or session.user_id != actor.id:
                raise SessionNotFoundError(f"Session {command.session_id} not found.")
            await repos.sessions.delete(session.id)
            await self._uow.commit()

        logger.info(
            "session revoked",
            user_id=actor.id,
            session_id=command.session_id,
        )
