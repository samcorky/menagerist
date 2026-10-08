from typing import TYPE_CHECKING

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.modules.collections.adapters.persistence.models import CollectionModel
from app.modules.collections.domain.collection import (
    Collection,
    CollectionKind,
    Visibility,
)
from app.shared_kernel.errors import ConflictError
from app.shared_kernel.slug import Slug

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


def _to_domain(model: CollectionModel) -> Collection:
    """Convert an ORM row into the domain entity."""
    return Collection(
        id=model.id,
        name=model.name,
        slug=Slug(model.slug),
        description=model.description,
        kind=CollectionKind(model.kind),
        owner_id=model.owner_id,
        visibility=Visibility(model.visibility),
        created_at=model.created_at,
        updated_at=model.updated_at,
        deleted_at=model.deleted_at,
    )


def _to_model(collection: Collection) -> CollectionModel:
    """Convert a domain entity into its ORM row."""
    return CollectionModel(
        id=collection.id,
        name=collection.name,
        slug=str(collection.slug),
        description=collection.description,
        kind=collection.kind.value,
        owner_id=collection.owner_id,
        visibility=collection.visibility.value,
        created_at=collection.created_at,
        updated_at=collection.updated_at,
        deleted_at=collection.deleted_at,
    )


class SqlAlchemyCollectionRepository:
    """Postgres-backed `CollectionRepository`, scoped to one session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, collection: Collection) -> None:
        """Add a new collection.

        Raises:
            ConflictError: If a live collection already uses the slug.
        """
        logger.debug("adding collection", collection_id=collection.id)
        try:
            # A savepoint keeps the session usable after a rejected insert.
            async with self._session.begin_nested():
                self._session.add(_to_model(collection))
        except IntegrityError as exc:
            raise ConflictError(
                f"A collection with slug '{collection.slug}' already exists"
            ) from exc

    async def save(self, collection: Collection) -> None:
        """Persist changes to an existing collection, including soft deletion."""
        logger.debug("saving collection", collection_id=collection.id)
        await self._session.merge(_to_model(collection))
        await self._session.flush()

    async def get(self, collection_id: uuid.UUID) -> Collection | None:
        """Return the live collection with `collection_id`, or `None`."""
        model = await self._session.get(CollectionModel, collection_id)
        if model is None or model.deleted_at is not None:
            return None
        return _to_domain(model)

    async def get_by_slug(self, slug: str) -> Collection | None:
        """Return the live collection with `slug`, or `None`."""
        stmt = select(CollectionModel).where(
            CollectionModel.slug == slug, CollectionModel.deleted_at.is_(None)
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return None if model is None else _to_domain(model)

    async def list(self, *, after: uuid.UUID | None, limit: int) -> list[Collection]:
        """Return up to `limit` live collections ordered by id, after `after`."""
        stmt = (
            select(CollectionModel)
            .where(CollectionModel.deleted_at.is_(None))
            .order_by(CollectionModel.id)
            .limit(limit)
        )
        if after is not None:
            stmt = stmt.where(CollectionModel.id > after)
        return [_to_domain(m) for m in (await self._session.execute(stmt)).scalars()]
