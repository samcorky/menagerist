from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import uuid

    from app.modules.identity.domain.user import User


class UserRepository(Protocol):
    """Access to user accounts, independent of storage backend."""

    async def add(self, user: User) -> None:
        """Add a new user.

        Raises:
            UsernameTakenError: If the username is taken (ignoring case).
        """
        ...

    async def save(self, user: User) -> None:
        """Persist changes to an existing user."""
        ...

    async def get(self, user_id: uuid.UUID) -> User | None:
        """Return the user with `user_id`, or `None`."""
        ...

    async def get_for_update(self, user_id: uuid.UUID) -> User | None:
        """Like `get`, but locks the row until the transaction ends."""
        ...

    async def get_by_username(self, username: str) -> User | None:
        """Return the user whose username matches ignoring case, or `None`."""
        ...

    async def get_by_username_for_update(self, username: str) -> User | None:
        """Like `get_by_username`, but locks the row until the transaction ends."""
        ...

    async def list_all(self) -> list[User]:
        """Return every user ordered by id."""
        ...

    async def count(self) -> int:
        """Return the number of users."""
        ...

    async def lock_for_setup(self) -> None:
        """Serialise first-run setup: blocks until other setups have finished."""
        ...

    async def lock_admin_changes(self) -> None:
        """Serialise changes that could remove an admin: blocks until others finish.

        Take it before any user row lock so every writer uses one order.
        """
        ...

    async def count_admins(self) -> int:
        """Return the number of enabled administrators."""
        ...
