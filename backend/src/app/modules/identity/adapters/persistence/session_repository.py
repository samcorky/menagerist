from typing import TYPE_CHECKING

import structlog
from sqlalchemy import CursorResult, delete, select

from app.modules.identity.adapters.persistence.models import SessionModel
from app.modules.identity.domain.session import Session

if TYPE_CHECKING:
    import uuid
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


def _to_domain(model: SessionModel) -> Session:
    """Convert an ORM row into the domain entity."""
    return Session(
        id=model.id,
        user_id=model.user_id,
        token_hash=model.token_hash,
        created_at=model.created_at,
        expires_at=model.expires_at,
        last_seen_at=model.last_seen_at,
        user_agent=model.user_agent,
        client_ip=model.client_ip,
        client_platform=model.client_platform,
        client_mobile=model.client_mobile,
    )


def _to_model(session: Session) -> SessionModel:
    """Convert a domain entity into its ORM row."""
    return SessionModel(
        id=session.id,
        user_id=session.user_id,
        token_hash=session.token_hash,
        created_at=session.created_at,
        expires_at=session.expires_at,
        last_seen_at=session.last_seen_at,
        user_agent=session.user_agent,
        client_ip=session.client_ip,
        client_platform=session.client_platform,
        client_mobile=session.client_mobile,
    )


class SqlAlchemySessionRepository:
    """Postgres-backed `SessionRepository`, scoped to one session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, session: Session) -> None:
        """Add a new session."""
        logger.debug("adding session", session_id=session.id)
        self._session.add(_to_model(session))
        await self._session.flush()

    async def save(self, session: Session) -> None:
        """Persist changes to an existing session (e.g. `last_seen_at`)."""
        await self._session.merge(_to_model(session))
        await self._session.flush()

    async def get(self, session_id: uuid.UUID) -> Session | None:
        """Return the session with `session_id`, or `None`."""
        stmt = select(SessionModel).where(SessionModel.id == session_id)
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return None if model is None else _to_domain(model)

    async def get_by_token_hash(self, token_hash: str) -> Session | None:
        """Return the session with `token_hash`, or `None`."""
        stmt = select(SessionModel).where(SessionModel.token_hash == token_hash)
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return None if model is None else _to_domain(model)

    async def list_for_user(
        self, user_id: uuid.UUID, *, now: datetime
    ) -> list[Session]:
        """Return non-expired sessions for `user_id`, newest `last_seen_at` first."""
        stmt = (
            select(SessionModel)
            .where(
                SessionModel.user_id == user_id,
                SessionModel.expires_at > now,
            )
            .order_by(SessionModel.last_seen_at.desc())
        )
        models = (await self._session.execute(stmt)).scalars().all()
        return [_to_domain(m) for m in models]

    async def list_active(
        self, *, now: datetime, user_id: uuid.UUID | None = None
    ) -> list[Session]:
        """Return non-expired sessions, newest `last_seen_at` first."""
        stmt = select(SessionModel).where(SessionModel.expires_at > now)
        if user_id is not None:
            stmt = stmt.where(SessionModel.user_id == user_id)
        stmt = stmt.order_by(SessionModel.last_seen_at.desc())
        models = (await self._session.execute(stmt)).scalars().all()
        return [_to_domain(m) for m in models]

    async def delete(self, session_id: uuid.UUID) -> None:
        """Remove one session; unknown ids are ignored."""
        await self._session.execute(
            delete(SessionModel).where(SessionModel.id == session_id)
        )

    async def delete_for_user(self, user_id: uuid.UUID) -> int:
        """Remove every session belonging to `user_id`, returning how many went."""
        result = await self._session.execute(
            delete(SessionModel).where(SessionModel.user_id == user_id)
        )
        assert isinstance(result, CursorResult)
        return result.rowcount

    async def delete_all_except(self, user_id: uuid.UUID, keep_id: uuid.UUID) -> int:
        """Remove sessions for `user_id` except `keep_id`, returning count."""
        result = await self._session.execute(
            delete(SessionModel).where(
                SessionModel.user_id == user_id,
                SessionModel.id != keep_id,
            )
        )
        assert isinstance(result, CursorResult)
        return result.rowcount

    async def delete_expired(self, now: datetime) -> int:
        """Remove sessions expired at `now`, returning how many went."""
        result = await self._session.execute(
            delete(SessionModel).where(SessionModel.expires_at <= now)
        )
        assert isinstance(result, CursorResult)
        return result.rowcount
