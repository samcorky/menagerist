from typing import TYPE_CHECKING

import structlog
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.modules.identity.adapters.persistence.models import UserModel
from app.modules.identity.domain.errors import UsernameTakenError
from app.modules.identity.domain.user import Role, User
from app.platform.advisory_locks import SETUP_LOCK_KEY

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

_ADMIN_LOCK_KEY = 7_302_024_002


def _to_domain(model: UserModel) -> User:
    """Convert an ORM row into the domain entity."""
    return User(
        id=model.id,
        username=model.username,
        display_name=model.display_name,
        password_hash=model.password_hash,
        role=Role(model.role),
        password_expired=model.password_expired,
        disabled=model.disabled,
        last_login_at=model.last_login_at,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _to_model(user: User) -> UserModel:
    """Convert a domain entity into its ORM row."""
    return UserModel(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        password_hash=user.password_hash,
        role=user.role.value,
        password_expired=user.password_expired,
        disabled=user.disabled,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


class SqlAlchemyUserRepository:
    """Postgres-backed `UserRepository`, scoped to one session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, user: User) -> None:
        """Add a new user.

        Raises:
            UsernameTakenError: If the username is taken (ignoring case).
        """
        logger.debug("adding user", user_id=user.id)
        try:
            # A savepoint keeps the session usable after a rejected insert.
            async with self._session.begin_nested():
                self._session.add(_to_model(user))
        except IntegrityError as exc:
            raise UsernameTakenError("That username is already taken.") from exc

    async def save(self, user: User) -> None:
        """Persist changes to an existing user."""
        logger.debug("saving user", user_id=user.id)
        await self._session.merge(_to_model(user))
        await self._session.flush()

    async def get(self, user_id: uuid.UUID) -> User | None:
        """Return the user with `user_id`, or `None`."""
        model = await self._session.get(UserModel, user_id)
        return None if model is None else _to_domain(model)

    async def get_for_update(self, user_id: uuid.UUID) -> User | None:
        """Like `get`, but locks the row until the transaction ends."""
        stmt = (
            select(UserModel)
            .where(UserModel.id == user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return None if model is None else _to_domain(model)

    async def get_by_username(self, username: str) -> User | None:
        """Return the user whose username matches ignoring case, or `None`."""
        stmt = select(UserModel).where(UserModel.username == username.lower())
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return None if model is None else _to_domain(model)

    async def get_by_username_for_update(self, username: str) -> User | None:
        """Like `get_by_username`, but locks the row until the transaction ends."""
        stmt = (
            select(UserModel)
            .where(UserModel.username == username.lower())
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return None if model is None else _to_domain(model)

    async def list_all(self) -> list[User]:
        """Return every user ordered by id."""
        stmt = select(UserModel).order_by(UserModel.id)
        return [_to_domain(m) for m in (await self._session.execute(stmt)).scalars()]

    async def count(self) -> int:
        """Return the number of users."""
        stmt = select(func.count()).select_from(UserModel)
        return (await self._session.execute(stmt)).scalar_one()

    async def lock_for_setup(self) -> None:
        """Take a transaction-scoped advisory lock so setups run one at a time."""
        await self._session.execute(select(func.pg_advisory_xact_lock(SETUP_LOCK_KEY)))

    async def lock_admin_changes(self) -> None:
        """Take a transaction-scoped advisory lock for admin-removing changes."""
        await self._session.execute(select(func.pg_advisory_xact_lock(_ADMIN_LOCK_KEY)))

    async def count_admins(self) -> int:
        """Return the number of enabled administrators."""
        stmt = (
            select(func.count())
            .select_from(UserModel)
            .where(UserModel.role == Role.ADMIN.value, UserModel.disabled.is_(False))
        )
        return (await self._session.execute(stmt)).scalar_one()
