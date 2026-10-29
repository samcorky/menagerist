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
from app.modules.identity.application.sign_in_throttle import SignInThrottle  # noqa: TC001
from app.modules.identity.domain.api_token import ApiToken
from app.modules.identity.domain.errors import (
    ApiTokenLimitError,
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
class CreateApiTokenCommand:
    """Request for a new personal access token."""

    name: str
    password: str
    grants: frozenset[str]
    expires_in_days: int | None
    client_ip: str | None = None

    def __repr__(self) -> str:
        """Keep the password out of logs and tracebacks."""
        return f"CreateApiTokenCommand(name={self.name!r})"


@dataclass(kw_only=True, frozen=True)
class CreatedApiToken:
    """A stored token and its plaintext, which is shown once and never kept."""

    token: ApiToken
    plaintext: str

    def __repr__(self) -> str:
        """Keep the plaintext out of logs and tracebacks."""
        return f"CreatedApiToken(token_id={self.token.id!r})"


class CreateApiToken(
    CommandHandler[IdentityUnitOfWork, CreateApiTokenCommand, CreatedApiToken]
):
    """Issue a token that acts as the user with a subset of their permissions."""

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
        grantable: frozenset[str],
        default_days: int,
        max_days: int,
        max_tokens: int,
    ) -> None:
        super().__init__(uow, guard)
        self._gate = PasswordGate(uow, hasher, throttle)
        self._tokens = tokens
        self._authorisation = authorisation
        self._grantable = grantable
        self._default_days = default_days
        self._max_days = max_days
        self._max_tokens = max_tokens

    async def _validated_grants(
        self, command: CreateApiTokenCommand, actor: Actor
    ) -> frozenset[str]:
        if not command.grants:
            raise InvalidApiTokenRequestError("A token needs at least one permission.")
        if not command.grants <= self._grantable:
            raise InvalidApiTokenRequestError("A token cannot have that permission.")
        held = await held_grants(self._authorisation, actor, command.grants)
        if held != command.grants:
            raise InvalidApiTokenRequestError(
                "A token cannot have a permission you do not hold."
            )
        return held

    async def _handle(
        self, command: CreateApiTokenCommand, actor: Actor
    ) -> CreatedApiToken:
        """Create the token, returning it with its one-time plaintext.

        Raises:
            InvalidApiTokenRequestError: If the name, permissions or lifetime are
                not acceptable.
            SignInThrottledError: If this user or address has failed too often.
            UserNotFoundError: If the acting account no longer exists.
            CurrentPasswordIncorrectError: If the password is wrong.
            ApiTokenLimitError: If the user already holds the maximum.
        """
        now = utc_now()
        grants = await self._validated_grants(command, actor)
        lifetime = resolve_lifetime(
            command.expires_in_days,
            default_days=self._default_days,
            max_days=self._max_days,
        )
        new = self._tokens.new_token()
        token = build_token(
            self._tokens,
            new,
            user_id=actor.id,
            name=command.name,
            grants=grants,
            now=now,
            lifetime=lifetime,
        )
        reservation = await self._gate.reserve(actor, command.client_ip, now)
        async with self._uow as repos:
            await self._gate.verify(repos, actor, command.password, reservation)
            if await repos.tokens.count_active(actor.id, now=now) >= self._max_tokens:
                await self._uow.commit()
                raise ApiTokenLimitError(
                    f"You can have at most {self._max_tokens} active tokens."
                )
            await repos.tokens.add(token)
            await self._uow.commit()
        logger.info(
            "api token created",
            user_id=actor.id,
            token_id=token.id,
            expires_at=token.expires_at.isoformat(),
        )
        return CreatedApiToken(token=token, plaintext=new.plaintext)
