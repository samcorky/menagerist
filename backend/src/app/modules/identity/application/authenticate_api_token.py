import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.identity.application.api_token_issue import utc_now
from app.modules.identity.application.get_current_user import LAST_SEEN_INTERVAL
from app.modules.identity.domain.user import User
from app.modules.identity.ports.api_token_generator import (  # noqa: TC001
    ApiTokenGenerator,
)
from app.modules.identity.ports.unit_of_work import IdentityUnitOfWork
from app.shared_kernel.access import Access, Public
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class AuthenticateApiTokenCommand:
    """Request to resolve a presented token value to its owner."""

    value: str

    def __repr__(self) -> str:
        """Keep the token out of logs and tracebacks."""
        return "AuthenticateApiTokenCommand()"


@dataclass(kw_only=True, frozen=True)
class ResolvedApiToken:
    """A valid token's owner, its row id (not a secret) and its grants."""

    user: User
    token_id: uuid.UUID
    grants: frozenset[str]


class AuthenticateApiToken(
    CommandHandler[
        IdentityUnitOfWork, AuthenticateApiTokenCommand, ResolvedApiToken | None
    ]
):
    """Resolve a token value to its owner and grants.

    A command handler because it records use: `last_used_at` moves at most once
    a minute. An unknown id costs the same hash and comparison as a wrong secret.
    """

    access: ClassVar[Access] = Public()

    def __init__(
        self, uow: IdentityUnitOfWork, guard: AccessGuard, tokens: ApiTokenGenerator
    ) -> None:
        super().__init__(uow, guard)
        self._tokens = tokens
        self._decoy_hash = tokens.hash("decoy")

    async def _handle(
        self, command: AuthenticateApiTokenCommand, actor: Actor
    ) -> ResolvedApiToken | None:
        """Return the owner and grants, or `None` if the token is unusable.

        Unusable means malformed, unknown, wrong secret, expired (the row is
        removed) or owned by a disabled user.
        """
        parsed = self._tokens.parse(command.value)
        if parsed is None:
            return None
        now = utc_now()
        async with self._uow as repos:
            token = await repos.tokens.get(parsed.token_id)
            stored = self._decoy_hash if token is None else token.secret_hash
            matched = self._tokens.matches(parsed.secret, stored)
            if token is None or not matched:
                return None
            if token.is_expired(now):
                await repos.tokens.delete(token.id)
                await self._uow.commit()
                return None
            user = await repos.users.get(token.user_id)
            if user is None or user.disabled:
                return None
            if (
                token.last_used_at is None
                or now - token.last_used_at >= LAST_SEEN_INTERVAL
            ):
                token.used(now)
                await repos.tokens.save(token)
                await self._uow.commit()
            return ResolvedApiToken(user=user, token_id=token.id, grants=token.grants)
