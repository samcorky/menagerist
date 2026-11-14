import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.identity.ports.unit_of_work import IdentityUnitOfWork
from app.shared_kernel.access import Access, OwnAccount
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True, frozen=True)
class RevokeOtherSessionsCommand:
    """Request to end all of the calling user's sessions except the current one."""

    current_session_id: uuid.UUID


class RevokeOtherSessions(
    CommandHandler[IdentityUnitOfWork, RevokeOtherSessionsCommand, int]
):
    """Sign out everywhere except this device.

    Ends every other session of the calling user and forgets every other
    remembered browser, so their device cookies lose the higher sign-in limit.
    """

    access: ClassVar[Access] = OwnAccount()

    async def _handle(self, command: RevokeOtherSessionsCommand, actor: Actor) -> int:
        """Revoke all sessions for `actor` except `command.current_session_id`."""
        async with self._uow as repos:
            current = await repos.sessions.get(command.current_session_id)
            ended = await repos.sessions.delete_all_except(
                actor.id, command.current_session_id
            )
            forgotten = await repos.devices.delete_for_user(
                actor.id, keep_id=current.device_id if current is not None else None
            )
            await self._uow.commit()

        logger.info(
            "other sessions revoked",
            user_id=actor.id,
            current_session_id=command.current_session_id,
            count=ended,
            devices=forgotten,
        )
        return ended
