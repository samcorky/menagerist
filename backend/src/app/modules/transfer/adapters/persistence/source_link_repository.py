from typing import TYPE_CHECKING

import structlog
from sqlalchemy import select

from app.modules.transfer.adapters.persistence.models import SourceLinkModel
from app.modules.transfer.domain.entity_kind import EntityKind
from app.modules.transfer.domain.source_link import SourceLink
from app.platform.orm_mixins import owned_by

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.shared_kernel.content_filter import ContentFilter

logger = structlog.get_logger()


def _to_domain(model: SourceLinkModel) -> SourceLink:
    return SourceLink(
        id=model.id,
        owner_id=model.owner_id,
        source=model.source,
        kind=EntityKind(model.kind),
        key=model.key,
        entity_id=model.entity_id,
        fields=dict(model.fields),
        imported_at=model.imported_at,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _to_model(link: SourceLink) -> SourceLinkModel:
    return SourceLinkModel(
        id=link.id,
        owner_id=link.owner_id,
        source=link.source,
        kind=link.kind.value,
        key=link.key,
        entity_id=link.entity_id,
        fields=dict(link.fields),
        imported_at=link.imported_at,
        created_at=link.created_at,
        updated_at=link.updated_at,
    )


class SqlAlchemySourceLinkRepository:
    """Postgres-backed `SourceLinkRepository`, scoped to one session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, link: SourceLink) -> None:
        """Add a new link."""
        logger.debug("adding source link", link_id=link.id)
        self._session.add(_to_model(link))
        await self._session.flush()

    async def save(self, link: SourceLink) -> None:
        """Persist changes to an existing link."""
        logger.debug("saving source link", link_id=link.id)
        await self._session.merge(_to_model(link))
        await self._session.flush()

    async def get_by_key(
        self, source: str, kind: EntityKind, key: str, *, scope: ContentFilter
    ) -> SourceLink | None:
        """Return the link for `key` of `kind` in `source`, or `None`."""
        stmt = (
            select(SourceLinkModel)
            .where(
                SourceLinkModel.source == source,
                SourceLinkModel.kind == kind.value,
                SourceLinkModel.key == key,
                owned_by(SourceLinkModel, scope.user_id),
            )
            .order_by(SourceLinkModel.id)
            .limit(1)
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return None if model is None else _to_domain(model)

    async def list_by_keys(
        self,
        source: str,
        kind: EntityKind,
        keys: Sequence[str],
        *,
        scope: ContentFilter,
    ) -> list[SourceLink]:
        """Return the links for those of `keys` that have one."""
        if not keys:
            return []
        stmt = (
            select(SourceLinkModel)
            .where(
                SourceLinkModel.source == source,
                SourceLinkModel.kind == kind.value,
                SourceLinkModel.key.in_(keys),
                owned_by(SourceLinkModel, scope.user_id),
            )
            .order_by(SourceLinkModel.id)
        )
        return [_to_domain(m) for m in (await self._session.execute(stmt)).scalars()]

    async def list_for_source(
        self, source: str, *, scope: ContentFilter
    ) -> list[SourceLink]:
        """Return every link of `source`, of every kind."""
        stmt = (
            select(SourceLinkModel)
            .where(
                SourceLinkModel.source == source,
                owned_by(SourceLinkModel, scope.user_id),
            )
            .order_by(SourceLinkModel.id)
        )
        return [_to_domain(m) for m in (await self._session.execute(stmt)).scalars()]
