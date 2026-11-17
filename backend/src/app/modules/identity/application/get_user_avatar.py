import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from app.modules.identity.application.permissions import IdentityPermission
from app.modules.identity.domain.avatar import AVATAR_SIZES
from app.modules.identity.domain.errors import AvatarNotFoundError
from app.modules.identity.ports.unit_of_work import IdentityRepos
from app.shared_kernel.access import Access, Requires
from app.shared_kernel.cqrs import QueryHandler

if TYPE_CHECKING:
    from app.modules.identity.ports.avatar_storage import AvatarStorage
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor

_MISSING = "That picture does not exist."


@dataclass(kw_only=True)
class GetUserAvatarQuery:
    """Request for one size of an account's current picture."""

    user_id: uuid.UUID
    version: str
    size: int
    # False for a revalidation: everything is checked, but the file is not read.
    include_bytes: bool = True


class GetUserAvatar(QueryHandler[IdentityRepos, GetUserAvatarQuery, bytes]):
    """Load an account's picture, for anyone signed in."""

    access: ClassVar[Access] = Requires(IdentityPermission.VIEW_PICTURES)

    def __init__(
        self, repos: IdentityRepos, guard: AccessGuard, storage: AvatarStorage
    ) -> None:
        super().__init__(repos, guard)
        self._storage = storage

    async def _handle(self, query: GetUserAvatarQuery, actor: Actor) -> bytes:
        """Return the WebP bytes of the current version at `size`.

        Raises:
            ForbiddenError: If `actor` is not a signed-in member or administrator.
            AvatarNotFoundError: If the account is missing, shows its initials, has
                moved on to another version, or `size` is not stored.
        """
        if query.size not in AVATAR_SIZES:
            raise AvatarNotFoundError(_MISSING)
        user = await self._repos.users.get(query.user_id)
        if user is None or user.avatar is None or user.avatar.version != query.version:
            raise AvatarNotFoundError(_MISSING)
        if not query.include_bytes:
            return b""
        data = await self._storage.read(query.user_id, query.version, query.size)
        if data is None:
            raise AvatarNotFoundError(_MISSING)
        return data
