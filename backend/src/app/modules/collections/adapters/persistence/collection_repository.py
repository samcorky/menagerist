from typing import TYPE_CHECKING

import structlog
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.modules.collections.adapters.persistence.models import CollectionModel
from app.modules.collections.domain.collection import (
    Collection,
    CollectionKind,
    Visibility,
)
from app.platform.orm_mixins import claim_rows, owned_by
from app.shared_kernel.errors import ConflictError
from app.shared_kernel.slug import Slug

if TYPE_CHECKING:
    import uuid

    from sqlalchemy import ColumnElement
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import InstrumentedAttribute

    from app.shared_kernel.content_filter import ContentFilter

logger = structlog.get_logger()


_LIKE_ESCAPE = "\\"


def _like_pattern(q: str) -> str:
    """Return a contains-pattern for `q` with LIKE wildcards escaped."""
    escaped = q.replace(_LIKE_ESCAPE, _LIKE_ESCAPE * 2)
    escaped = escaped.replace("%", _LIKE_ESCAPE + "%").replace("_", _LIKE_ESCAPE + "_")
    return f"%{escaped}%"


def _unaccent_ilike(
    column_: InstrumentedAttribute[str] | InstrumentedAttribute[str | None],
    pattern: str,
) -> ColumnElement[bool]:
    """Case- and accent-insensitive LIKE of `column_` against an escaped `pattern`."""
    return func.unaccent(column_).ilike(func.unaccent(pattern), escape=_LIKE_ESCAPE)


def _in_scope(scope: ContentFilter) -> ColumnElement[bool]:
    """Live collections whose owner is inside `scope`."""
    return CollectionModel.deleted_at.is_(None) & owned_by(
        CollectionModel, scope.user_id
    )


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
        definition=model.definition,
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
        definition=collection.definition,
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
            ConflictError: If a live collection of the same owner uses the slug.
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
        """Persist changes to an existing collection, including soft deletion.

        Raises:
            ConflictError: If a live collection of the same owner uses the slug.
        """
        logger.debug("saving collection", collection_id=collection.id)
        try:
            # A savepoint keeps the session usable after a rejected write.
            async with self._session.begin_nested():
                await self._session.merge(_to_model(collection))
                await self._session.flush()
        except IntegrityError as exc:
            raise ConflictError(
                f"A collection with slug '{collection.slug}' already exists"
            ) from exc

    async def get(
        self, collection_id: uuid.UUID, *, scope: ContentFilter
    ) -> Collection | None:
        """Return the live collection with `collection_id` in `scope`, or `None`."""
        stmt = (
            select(CollectionModel)
            .where(_in_scope(scope), CollectionModel.id == collection_id)
            # A read session may outlive a commit made through another session.
            .execution_options(populate_existing=True)
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return None if model is None else _to_domain(model)

    async def get_by_slug(
        self, slug: str, *, scope: ContentFilter
    ) -> Collection | None:
        """Return the live collection with `slug` in `scope`, or `None`.

        Slugs are unique per owner, so under `everyone()` the lowest id wins.
        """
        stmt = (
            select(CollectionModel)
            .where(_in_scope(scope), CollectionModel.slug == slug)
            .order_by(CollectionModel.id)
            .limit(1)
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return None if model is None else _to_domain(model)

    async def list(
        self,
        *,
        scope: ContentFilter,
        after: uuid.UUID | None,
        limit: int,
        q: str | None = None,
        kind: CollectionKind | None = None,
    ) -> list[Collection]:
        """Return up to `limit` live collections in `scope`, ordered by id.

        A non-blank `q` keeps collections whose name or description contains it,
        ignoring case and accents. A `kind` keeps only collections of that kind.
        """
        stmt = (
            select(CollectionModel)
            .where(_in_scope(scope))
            .order_by(CollectionModel.id)
            .limit(limit)
        )
        if after is not None:
            stmt = stmt.where(CollectionModel.id > after)
        if kind is not None:
            stmt = stmt.where(CollectionModel.kind == kind.value)
        needle = (q or "").strip()
        if needle:
            pattern = _like_pattern(needle)
            stmt = stmt.where(
                _unaccent_ilike(CollectionModel.name, pattern)
                | _unaccent_ilike(CollectionModel.description, pattern)
            )
        return [_to_domain(m) for m in (await self._session.execute(stmt)).scalars()]

    async def claim_orphaned(
        self, owner_id: uuid.UUID, *, legacy_owner_ids: frozenset[uuid.UUID]
    ) -> int:
        """Give `owner_id` every collection with no owner or a legacy owner."""
        return await claim_rows(
            self._session, CollectionModel, owner_id, legacy_owner_ids
        )
