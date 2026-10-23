from typing import TYPE_CHECKING

import structlog
from sqlalchemy import CursorResult, delete, func, select

from app.modules.identity.adapters.persistence.models import ApiTokenModel
from app.modules.identity.domain.api_token import ApiToken

if TYPE_CHECKING:
    import uuid
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


def _to_domain(model: ApiTokenModel) -> ApiToken:
    """Convert an ORM row into the domain entity."""
    return ApiToken(
        id=model.id,
        user_id=model.user_id,
        name=model.name,
        secret_hash=model.secret_hash,
        grants=frozenset(model.grants),
        created_at=model.created_at,
        expires_at=model.expires_at,
        last_used_at=model.last_used_at,
    )


def _to_model(token: ApiToken) -> ApiTokenModel:
    """Convert a domain entity into its ORM row."""
    return ApiTokenModel(
        id=token.id,
        user_id=token.user_id,
        name=token.name,
        secret_hash=token.secret_hash,
        grants=sorted(token.grants),
        created_at=token.created_at,
        expires_at=token.expires_at,
        last_used_at=token.last_used_at,
    )


class SqlAlchemyApiTokenRepository:
    """Postgres-backed `ApiTokenRepository`, scoped to one session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, token: ApiToken) -> None:
        """Add a new token."""
        logger.debug("adding api token", token_id=token.id)
        self._session.add(_to_model(token))
        await self._session.flush()

    async def save(self, token: ApiToken) -> None:
        """Persist changes to an existing token (e.g. `last_used_at`)."""
        await self._session.merge(_to_model(token))
        await self._session.flush()

    async def get(self, token_id: uuid.UUID) -> ApiToken | None:
        """Return the token with `token_id`, or `None`."""
        stmt = select(ApiTokenModel).where(ApiTokenModel.id == token_id)
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return None if model is None else _to_domain(model)

    async def list_for_user(
        self, user_id: uuid.UUID, *, now: datetime
    ) -> list[ApiToken]:
        """Return unexpired tokens for `user_id`, newest `created_at` first."""
        stmt = (
            select(ApiTokenModel)
            .where(ApiTokenModel.user_id == user_id, ApiTokenModel.expires_at > now)
            .order_by(ApiTokenModel.created_at.desc(), ApiTokenModel.id)
        )
        models = (await self._session.execute(stmt)).scalars().all()
        return [_to_domain(m) for m in models]

    async def count_active(self, user_id: uuid.UUID, *, now: datetime) -> int:
        """Return how many unexpired tokens `user_id` holds."""
        stmt = (
            select(func.count())
            .select_from(ApiTokenModel)
            .where(ApiTokenModel.user_id == user_id, ApiTokenModel.expires_at > now)
        )
        return (await self._session.execute(stmt)).scalar_one()

    async def delete(self, token_id: uuid.UUID) -> None:
        """Remove one token; unknown ids are ignored."""
        await self._session.execute(
            delete(ApiTokenModel).where(ApiTokenModel.id == token_id)
        )

    async def delete_for_user(self, user_id: uuid.UUID) -> int:
        """Remove every token belonging to `user_id`, returning how many went."""
        result = await self._session.execute(
            delete(ApiTokenModel).where(ApiTokenModel.user_id == user_id)
        )
        assert isinstance(result, CursorResult)
        return result.rowcount

    async def delete_expired(self, now: datetime) -> int:
        """Remove tokens expired at `now`, returning how many went."""
        result = await self._session.execute(
            delete(ApiTokenModel).where(ApiTokenModel.expires_at <= now)
        )
        assert isinstance(result, CursorResult)
        return result.rowcount
