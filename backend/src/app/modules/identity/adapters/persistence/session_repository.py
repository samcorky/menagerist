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

    async def get_by_token_hash(self, token_hash: str) -> Session | None:
        """Return the session with `token_hash`, or `None`."""
        stmt = select(SessionModel).where(SessionModel.token_hash == token_hash)
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return None if model is None else _to_domain(model)

    async def delete(self, session_id: uuid.UUID) -> None:
        """Remove one session; unknown ids are ignored."""
        await self._session.execute(
            delete(SessionModel).where(SessionModel.id == session_id)
        )

    async def delete_for_user(self, user_id: uuid.UUID) -> None:
        """Remove every session belonging to `user_id`."""
        await self._session.execute(
            delete(SessionModel).where(SessionModel.user_id == user_id)
        )

    async def delete_expired(self, now: datetime) -> int:
        """Remove sessions expired at `now`, returning how many went."""
        result = await self._session.execute(
            delete(SessionModel).where(SessionModel.expires_at <= now)
        )
        assert isinstance(result, CursorResult)
        return result.rowcount
