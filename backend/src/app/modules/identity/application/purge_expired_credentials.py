from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.identity.ports.unit_of_work import IdentityUnitOfWork
from app.shared_kernel.access import Access, System
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True, frozen=True)
class PurgeExpiredCredentialsCommand:
    """The instant to judge expiry against."""

    now: datetime


@dataclass(kw_only=True, frozen=True)
class PurgeExpiredCredentialsResult:
    """How many expired sessions and API tokens were removed."""

    sessions: int
    tokens: int


class PurgeExpiredCredentials(
    CommandHandler[
        IdentityUnitOfWork,
        PurgeExpiredCredentialsCommand,
        PurgeExpiredCredentialsResult,
    ]
):
    """Remove sessions and API tokens that are past their expiry."""

    access: ClassVar[Access] = System()

    async def _handle(
        self, command: PurgeExpiredCredentialsCommand, actor: Actor
    ) -> PurgeExpiredCredentialsResult:
        async with self._uow as repos:
            sessions = await repos.sessions.delete_expired(command.now)
            tokens = await repos.tokens.delete_expired(command.now)
            await self._uow.commit()
        logger.info("expired credentials purged", sessions=sessions, tokens=tokens)
        return PurgeExpiredCredentialsResult(sessions=sessions, tokens=tokens)
