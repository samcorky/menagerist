import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.identity.application.api_token_issue import (
    PasswordGate,
    build_token,
    held_grants,
    resolve_lifetime,
    utc_now,
)
from app.modules.identity.application.create_api_token import CreatedApiToken
from app.modules.identity.application.sign_in_throttle import SignInThrottle  # noqa: TC001
from app.modules.identity.domain.errors import (
    ApiTokenNotFoundError,
    InvalidApiTokenRequestError,
)
from app.modules.identity.ports.api_token_generator import ApiTokenGenerator  # noqa: TC001
from app.modules.identity.ports.password_hasher import PasswordHasher  # noqa: TC001
from app.modules.identity.ports.unit_of_work import IdentityUnitOfWork
from app.shared_kernel.access import Access, OwnAccount
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor
    from app.shared_kernel.authorisation import AuthorisationPort

logger = structlog.get_logger()


@dataclass(kw_only=True)
class RotateApiTokenCommand:
    """Request to replace one of the calling user's tokens with a fresh secret."""

    token_id: uuid.UUID
    password: str
    expires_in_days: int | None
    client_ip: str | None = None

    def __repr__(self) -> str:
        """Keep the password out of logs and tracebacks."""
        return f"RotateApiTokenCommand(token_id={self.token_id!r})"


class RotateApiToken(
    CommandHandler[IdentityUnitOfWork, RotateApiTokenCommand, CreatedApiToken]
):
    """Replace a token by one with the same name and grants, a new secret and expiry."""

    access: ClassVar[Access] = OwnAccount()

    def __init__(
        self,
        uow: IdentityUnitOfWork,
        guard: AccessGuard,
        hasher: PasswordHasher,
        tokens: ApiTokenGenerator,
        throttle: SignInThrottle,
        authorisation: AuthorisationPort,
        *,
        default_days: int,
        max_days: int,
    ) -> None:
        super().__init__(uow, guard)
        self._gate = PasswordGate(uow, hasher, throttle)
        self._tokens = tokens
        self._authorisation = authorisation
        self._default_days = default_days
        self._max_days = max_days

    async def _handle(
        self, command: RotateApiTokenCommand, actor: Actor
    ) -> CreatedApiToken:
        """Issue the replacement and delete the old token in one transaction.

        Grants the owner no longer holds are dropped from the replacement.

        Raises:
            InvalidApiTokenRequestError: If the lifetime is not acceptable or no
                grant remains.
            SignInThrottledError: If this user or address has failed too often.
            UserNotFoundError: If the acting account no longer exists.
            CurrentPasswordIncorrectError: If the password is wrong.
            ApiTokenNotFoundError: If unknown or owned by another user.
        """
        now = utc_now()
        lifetime = resolve_lifetime(
            command.expires_in_days,
            default_days=self._default_days,
            max_days=self._max_days,
        )
        reservation = await self._gate.reserve(actor, command.client_ip, now)
        async with self._uow as repos:
            await self._gate.verify(repos, actor, command.password, reservation)
            old = await repos.tokens.get(command.token_id)
            if old is None or old.user_id != actor.id or old.is_expired(now):
                await self._uow.commit()
                raise ApiTokenNotFoundError(f"Token {command.token_id} not found.")
            grants = await held_grants(self._authorisation, actor, old.grants)
            if not grants:
                await self._uow.commit()
                raise InvalidApiTokenRequestError(
                    "None of this token's permissions are held any more."
                )
            new = self._tokens.new_token()
            token = build_token(
                self._tokens,
                new,
                user_id=actor.id,
                name=old.name,
                grants=grants,
                now=now,
                lifetime=lifetime,
            )
            await repos.tokens.delete(old.id)
            await repos.tokens.add(token)
            await self._uow.commit()
        logger.info(
            "api token rotated",
            user_id=actor.id,
            old_token_id=old.id,
            token_id=token.id,
            expires_at=token.expires_at.isoformat(),
        )
        return CreatedApiToken(token=token, plaintext=new.plaintext)
