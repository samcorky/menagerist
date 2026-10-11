from typing import TYPE_CHECKING

from app.modules.identity.domain.errors import UsernameTakenError
from app.modules.identity.domain.user import Role

if TYPE_CHECKING:
    import uuid

    from app.modules.identity.domain.user import User


class InMemoryUserRepository:
    """Dict-backed `UserRepository` for tests."""

    def __init__(self) -> None:
        self._users: dict[uuid.UUID, User] = {}

    async def add(self, user: User) -> None:
        """Add a new user.

        Raises:
            UsernameTakenError: If the username is taken (ignoring case).
        """
        if await self.get_by_username(user.username) is not None:
            raise UsernameTakenError("That username is already taken.")
        self._users[user.id] = user

    async def save(self, user: User) -> None:
        """Persist changes to an existing user."""
        self._users[user.id] = user

    async def get(self, user_id: uuid.UUID) -> User | None:
        """Return the user with `user_id`, or `None`."""
        return self._users.get(user_id)

    async def get_for_update(self, user_id: uuid.UUID) -> User | None:
        """Like `get`; there is nothing to lock in memory."""
        return await self.get(user_id)

    async def get_by_username(self, username: str) -> User | None:
        """Return the user whose username matches ignoring case, or `None`."""
        wanted = username.lower()
        return next((u for u in self._users.values() if u.username == wanted), None)

    async def get_by_username_for_update(self, username: str) -> User | None:
        """Like `get_by_username`; there is nothing to lock in memory."""
        return await self.get_by_username(username)

    async def list_all(self) -> list[User]:
        """Return every user ordered by id."""
        return sorted(self._users.values(), key=lambda u: u.id)

    async def count(self) -> int:
        """Return the number of users."""
        return len(self._users)

    async def lock_for_setup(self) -> None:
        """Nothing to serialise in memory."""

    async def lock_admin_changes(self) -> None:
        """Nothing to serialise in memory."""

    async def count_admins(self) -> int:
        """Return the number of enabled administrators."""
        return sum(
            1 for u in self._users.values() if u.role is Role.ADMIN and not u.disabled
        )
