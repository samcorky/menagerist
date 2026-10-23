import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.identity.domain.errors import ApiTokenNotFoundError
from app.modules.identity.ports.unit_of_work import IdentityUnitOfWork
from app.shared_kernel.access import Access, OwnAccount
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True, frozen=True)
class RevokeOwnApiTokenCommand:
    """Request to revoke one of the calling user's tokens."""

    token_id: uuid.UUID


class RevokeOwnApiToken(
    CommandHandler[IdentityUnitOfWork, RevokeOwnApiTokenCommand, None]
):
    """Delete one of the user's tokens; it stops working at once."""

    access: ClassVar[Access] = OwnAccount()

    async def _handle(self, command: RevokeOwnApiTokenCommand, actor: Actor) -> None:
        """Revoke the token if it belongs to `actor`.

        Raises:
            ApiTokenNotFoundError: If unknown or owned by another user.
        """
        async with self._uow as repos:
            token = await repos.tokens.get(command.token_id)
            if token is None or token.user_id != actor.id:
                raise ApiTokenNotFoundError(f"Token {command.token_id} not found.")
            await repos.tokens.delete(token.id)
            await self._uow.commit()
        logger.info("api token revoked", user_id=actor.id, token_id=command.token_id)
