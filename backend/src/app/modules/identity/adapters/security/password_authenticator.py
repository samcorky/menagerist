import asyncio
import math
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.modules.identity.domain.errors import SignInThrottledError
from app.modules.identity.ports.authenticator import VerifiedIdentity

if TYPE_CHECKING:
    from app.modules.identity.domain.user import User
    from app.modules.identity.ports.authenticator import PasswordCredentials
    from app.modules.identity.ports.password_hasher import PasswordHasher
    from app.modules.identity.ports.unit_of_work import IdentityUnitOfWork


class PasswordAuthenticator:
    """Local `Authenticator`: username and password against the users table.

    Applies the lockout rules and upgrades outdated hashes on success. The
    outcome is recorded under a row lock, so concurrent guesses and admin
    changes cannot interleave with the failure count.
    """

    def __init__(
        self, uow: IdentityUnitOfWork, hasher: PasswordHasher, *, decoy_hash: str
    ) -> None:
        """Wire the authenticator.

        `decoy_hash` is a hash made once per process (by the composition root)
        so unknown and disabled usernames cost one verify, like real ones.
        """
        self._uow = uow
        self._hasher = hasher
        self._decoy_hash = decoy_hash

    async def authenticate(
        self, credentials: PasswordCredentials
    ) -> VerifiedIdentity | None:
        """Return the verified identity, or `None` if the credentials are wrong.

        The slow hashing runs with no transaction open, so a flood of attempts
        cannot hold every database connection. The user is read first, the
        password checked, then the row locked and its state re-checked before
        the outcome is recorded.

        Raises:
            SignInThrottledError: If the account is locked after repeated failures.
        """
        now = datetime.now(UTC)
        async with self._uow as repos:
            user = await repos.users.get_by_username(credentials.username)
            if user is not None and not user.disabled:
                self._raise_if_locked(user, now)
                seen_hash = user.password_hash
            else:
                seen_hash = None
        if seen_hash is None:
            # Spend comparable time so unknown names are not distinguishable.
            await asyncio.to_thread(
                self._hasher.verify, credentials.password, self._decoy_hash
            )
            return None

        matched = await asyncio.to_thread(
            self._hasher.verify, credentials.password, seen_hash
        )
        new_hash = None
        if matched and self._hasher.needs_rehash(seen_hash):
            new_hash = await asyncio.to_thread(self._hasher.hash, credentials.password)

        async with self._uow as repos:
            locked = await repos.users.get_by_username_for_update(credentials.username)
            if locked is None or locked.disabled or locked.password_hash != seen_hash:
                # Changed while verifying: the result no longer applies.
                return None
            self._raise_if_locked(locked, now)
            if not matched:
                locked.record_failure(now)
                await repos.users.save(locked)
                await self._uow.commit()
                return None
            locked.record_success()
            if new_hash is not None:
                locked.rehash(new_hash)
            await repos.users.save(locked)
            await self._uow.commit()
            return VerifiedIdentity(
                subject=locked.username, display_name=locked.display_name
            )

    @staticmethod
    def _raise_if_locked(user: User, now: datetime) -> None:
        locked_until = user.locked_until
        if locked_until is not None and user.is_locked(now):
            raise SignInThrottledError(
                "Too many failed attempts. Try again later.",
                retry_after=max(1, math.ceil((locked_until - now).total_seconds())),
            )
