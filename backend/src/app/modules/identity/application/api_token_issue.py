import asyncio
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from app.modules.identity.application.sign_in_throttle import (
    SignInThrottle,
    ip_key,
    user_id_key,
)
from app.modules.identity.domain.api_token import ApiToken
from app.modules.identity.domain.errors import (
    CurrentPasswordIncorrectError,
    InvalidApiTokenRequestError,
    UserNotFoundError,
)
from app.modules.identity.ports.password_hasher import PasswordHasher  # noqa: TC001
from app.modules.identity.ports.unit_of_work import IdentityRepos, IdentityUnitOfWork  # noqa: TC001
from app.shared_kernel.errors import ForbiddenError

if TYPE_CHECKING:
    import uuid
    from collections.abc import Iterable

    from app.modules.identity.application.sign_in_throttle import Reservation
    from app.modules.identity.domain.user import User
    from app.modules.identity.ports.api_token_generator import (
        ApiTokenGenerator,
        NewApiToken,
    )
    from app.shared_kernel.actor import Actor
    from app.shared_kernel.authorisation import AuthorisationPort


def resolve_lifetime(
    expires_in_days: int | None, *, default_days: int, max_days: int
) -> timedelta:
    """Return the lifetime requested, defaulting when `None`.

    Raises:
        InvalidApiTokenRequestError: If outside 1 to `max_days` days.
    """
    days = default_days if expires_in_days is None else expires_in_days
    if not 1 <= days <= max_days:
        msg = f"A token must last between 1 and {max_days} days."
        raise InvalidApiTokenRequestError(msg)
    return timedelta(days=days)


async def held_grants(
    authorisation: AuthorisationPort, actor: Actor, grants: Iterable[str]
) -> frozenset[str]:
    """Return the subset of `grants` that `actor` holds now."""
    held: set[str] = set()
    for grant in grants:
        try:
            await authorisation.check(actor, grant)
        except ForbiddenError:
            continue
        held.add(grant)
    return frozenset(held)


def build_token(
    generator: ApiTokenGenerator,
    new: NewApiToken,
    *,
    user_id: uuid.UUID,
    name: str,
    grants: frozenset[str],
    now: datetime,
    lifetime: timedelta,
) -> ApiToken:
    """Build the stored token for a freshly generated one."""
    return ApiToken.create(
        token_id=new.token_id,
        user_id=user_id,
        name=name,
        secret_hash=generator.hash(new.secret),
        grants=grants,
        now=now,
        expires_at=now + lifetime,
    )


class PasswordGate:
    """Throttled check of the acting user's password, as `ChangePassword` does."""

    def __init__(
        self,
        uow: IdentityUnitOfWork,
        hasher: PasswordHasher,
        throttle: SignInThrottle,
    ) -> None:
        self._uow = uow
        self._hasher = hasher
        self._throttle = throttle

    async def reserve(
        self, actor: Actor, client_ip: str | None, now: datetime
    ) -> Reservation:
        """Count the attempt before the password is checked.

        Raises:
            SignInThrottledError: If this user or address has failed too often.
        """
        keys = [user_id_key(actor.id)]
        if client_ip:
            keys.append(ip_key(client_ip))
        async with self._uow as repos:
            reservation = await self._throttle.reserve(repos.attempts, keys, now)
            await self._uow.commit()
        if reservation.locked_until is not None:
            raise self._throttle.throttled(reservation.locked_until, now)
        return reservation

    async def verify(
        self,
        repos: IdentityRepos,
        actor: Actor,
        password: str,
        reservation: Reservation,
    ) -> User:
        """Lock the user, check the password and clear the failure count.

        Raises:
            UserNotFoundError: If the acting account no longer exists.
            CurrentPasswordIncorrectError: If the password is wrong.
        """
        user = await repos.users.get_for_update(actor.id)
        if user is None:
            raise UserNotFoundError("That account does not exist.")
        if not await asyncio.to_thread(
            self._hasher.verify, password, user.password_hash
        ):
            raise CurrentPasswordIncorrectError("The current password is incorrect.")
        await self._throttle.settle_success(repos.attempts, reservation)
        return user


def utc_now() -> datetime:
    """Return the current instant, in UTC."""
    return datetime.now(UTC)
