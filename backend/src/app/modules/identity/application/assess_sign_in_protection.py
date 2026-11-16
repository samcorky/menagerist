"""Count what sign-in protection is holding locked, for the status page."""

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, ClassVar

from app.modules.identity.application.sign_in_throttle import user_id_key, username_key
from app.modules.identity.domain.throttle import ThrottleKind
from app.modules.identity.ports.unit_of_work import IdentityRepos
from app.shared_kernel.access import Access, System
from app.shared_kernel.cqrs import QueryHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

_ADDRESS_KINDS = frozenset({ThrottleKind.IP, ThrottleKind.TOKEN_IP})


@dataclass(kw_only=True, frozen=True)
class AssessSignInProtectionQuery:
    """The instant to judge locks against."""

    now: datetime


@dataclass(kw_only=True, frozen=True)
class SignInProtection:
    """Counts only: the locks are stored as hashes, so nothing here names anyone."""

    locked_accounts: int = 0
    # Locked sign-in names that match no account, which is what guessing looks like.
    unknown_names: int = 0
    locked_addresses: int = 0


class AssessSignInProtection(
    QueryHandler[IdentityRepos, AssessSignInProtectionQuery, SignInProtection]
):
    """Count locked accounts, unknown names and client addresses.

    An account counts as locked when either of its counters is (the username's, used
    at sign-in, and the user id's, used when a signed-in user changes their password),
    the same two keys `UnlockUser` clears. Locked remembered browsers are not counted:
    they belong to an account that can still sign in from elsewhere.
    """

    access: ClassVar[Access] = System()

    async def _handle(
        self, request: AssessSignInProtectionQuery, actor: Actor
    ) -> SignInProtection:
        locked = await self._repos.attempts.all_locked(now=request.now)
        if not locked:
            return SignInProtection()
        users = await self._repos.users.list_all()
        known_names = {username_key(user.username) for user in users}
        return SignInProtection(
            locked_accounts=sum(
                1
                for user in users
                if username_key(user.username) in locked
                or user_id_key(user.id) in locked
            ),
            unknown_names=sum(
                1
                for key in locked
                if key.kind is ThrottleKind.USERNAME and key not in known_names
            ),
            locked_addresses=sum(1 for key in locked if key.kind in _ADDRESS_KINDS),
        )
