import asyncio
from typing import TYPE_CHECKING

from app.modules.identity.domain.errors import AccountDisabledError
from app.modules.identity.ports.authenticator import VerifiedIdentity

if TYPE_CHECKING:
    from app.modules.identity.ports.authenticator import PasswordCredentials
    from app.modules.identity.ports.password_hasher import PasswordHasher
    from app.modules.identity.ports.unit_of_work import IdentityUnitOfWork


class PasswordAuthenticator:
    """Local `Authenticator`: username and password against the users table.

    Upgrades outdated hashes on success. Throttling is the caller's job (it
    must not depend on whether the account exists).
    """

    def __init__(
        self, uow: IdentityUnitOfWork, hasher: PasswordHasher, *, decoy_hash: str
    ) -> None:
        """Wire the authenticator.

        `decoy_hash` is a hash made once per process (by the composition root)
        so unknown usernames cost one verify, like real ones.
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
        password checked, then the row locked and re-checked before a hash
        upgrade is stored. A disabled account is revealed only after its
        password verified, so the answer is not a username oracle.

        Raises:
            AccountDisabledError: If the password is right but the account is
                disabled.
        """
        async with self._uow as repos:
            user = await repos.users.get_by_username(credentials.username)
        seen_hash = None if user is None else user.password_hash
        # Spend comparable time so unknown names are not distinguishable.
        matched = await asyncio.to_thread(
            self._hasher.verify, credentials.password, seen_hash or self._decoy_hash
        )
        if user is None or seen_hash is None or not matched:
            return None

        new_hash = None
        if self._hasher.needs_rehash(seen_hash):
            new_hash = await asyncio.to_thread(self._hasher.hash, credentials.password)

        async with self._uow as repos:
            locked = await repos.users.get_by_username_for_update(credentials.username)
            if locked is None or locked.password_hash != seen_hash:
                # Changed while verifying: the result no longer applies.
                return None
            if locked.disabled:
                raise AccountDisabledError()
            if new_hash is not None:
                locked.rehash(new_hash)
                await repos.users.save(locked)
                await self._uow.commit()
            return VerifiedIdentity(
                subject=locked.username,
                display_name=locked.display_name,
                credential_hash=locked.password_hash,
            )
