from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy import delete, select

from app.modules.transfer.adapters.persistence.models import ItemImportModel
from app.modules.transfer.domain.bundle import NameLookup
from app.modules.transfer.domain.item_import import (
    ImportOptions,
    ImportOutcome,
    ImportStatus,
    ItemImport,
)
from app.modules.transfer.domain.tabular import (
    ColumnMapping,
    ConnectionColumn,
    ConnectionEnd,
    DayMonthOrder,
    ExtraField,
    ExtraFieldKind,
)
from app.platform.orm_mixins import owned_by
from app.shared_kernel.progress import ProgressSnapshot

if TYPE_CHECKING:
    import uuid
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.shared_kernel.content_filter import ContentFilter

logger = structlog.get_logger()


def _mapping_to_json(entry: ColumnMapping) -> dict[str, Any]:
    extra = entry.extra
    return {
        "column": entry.column,
        "target": entry.target,
        "extra": None
        if extra is None
        else {"key": extra.key, "title": extra.title, "kind": extra.kind.value},
    }


def _mapping_from_json(data: dict[str, Any]) -> ColumnMapping:
    extra = data["extra"]
    return ColumnMapping(
        column=data["column"],
        target=data["target"],
        extra=None
        if extra is None
        else ExtraField(
            key=extra["key"], title=extra["title"], kind=ExtraFieldKind(extra["kind"])
        ),
    )


def _connection_to_json(column: ConnectionColumn) -> dict[str, Any]:
    return {
        "column": column.column,
        "relationship_type": column.relationship_type,
        "item_type": column.item_type,
        "row_end": column.row_end.value,
        "on_missing": column.on_missing.value,
    }


def _connection_from_json(data: dict[str, Any]) -> ConnectionColumn:
    return ConnectionColumn(
        column=data["column"],
        relationship_type=data["relationship_type"],
        item_type=data["item_type"],
        row_end=ConnectionEnd(data["row_end"]),
        on_missing=NameLookup(data["on_missing"]),
    )


def options_to_json(options: ImportOptions) -> dict[str, Any]:
    """Plain data for the `options` column."""
    return {
        "item_type": options.item_type,
        "mapping": [_mapping_to_json(m) for m in options.mapping],
        "list_separator": options.list_separator,
        "day_month_order": options.day_month_order.value,
        "key_field": options.key_field,
        "restore": list(options.restore),
        "connections": [_connection_to_json(c) for c in options.connections],
    }


def options_from_json(data: dict[str, Any]) -> ImportOptions:
    """Rebuild what `options_to_json` stored."""
    return ImportOptions(
        item_type=data["item_type"],
        mapping=tuple(_mapping_from_json(m) for m in data["mapping"]),
        list_separator=data["list_separator"],
        day_month_order=DayMonthOrder(data["day_month_order"]),
        key_field=data["key_field"],
        restore=tuple(data["restore"]),
        connections=tuple(_connection_from_json(c) for c in data["connections"]),
    )


def _to_domain(model: ItemImportModel) -> ItemImport:
    return ItemImport(
        id=model.id,
        owner_id=model.owner_id,
        filename=model.filename,
        size=model.size,
        status=ImportStatus(model.status),
        options=None if model.options is None else options_from_json(model.options),
        grants=None if model.grants is None else frozenset(model.grants),
        progress=(
            None
            if model.progress is None
            else ProgressSnapshot.from_dict(model.progress)
        ),
        outcome=None if model.outcome is None else ImportOutcome(**model.outcome),
        failure=model.failure,
        queued_at=model.queued_at,
        started_at=model.started_at,
        finished_at=model.finished_at,
        expires_at=model.expires_at,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _to_model(item: ItemImport) -> ItemImportModel:
    outcome = item.outcome
    return ItemImportModel(
        id=item.id,
        owner_id=item.owner_id,
        filename=item.filename,
        size=item.size,
        status=item.status.value,
        options=None if item.options is None else options_to_json(item.options),
        grants=None if item.grants is None else sorted(item.grants),
        progress=None if item.progress is None else item.progress.to_dict(),
        outcome=None
        if outcome is None
        else {
            "items_added": outcome.items_added,
            "connections_added": outcome.connections_added,
        },
        failure=item.failure,
        queued_at=item.queued_at,
        started_at=item.started_at,
        finished_at=item.finished_at,
        expires_at=item.expires_at,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


class SqlAlchemyItemImportRepository:
    """Postgres-backed `ItemImportRepository`, scoped to one session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, item: ItemImport) -> None:
        """Add a new import."""
        logger.debug("adding item import", import_id=item.id)
        self._session.add(_to_model(item))
        await self._session.flush()

    async def save(self, item: ItemImport) -> None:
        """Persist changes to an existing import."""
        await self._session.merge(_to_model(item))
        await self._session.flush()

    async def delete(self, import_id: uuid.UUID) -> None:
        """Remove an import; nothing happens if there is none."""
        await self._session.execute(
            delete(ItemImportModel).where(ItemImportModel.id == import_id)
        )

    async def get(
        self, import_id: uuid.UUID, *, scope: ContentFilter
    ) -> ItemImport | None:
        """Return the import with `import_id` within `scope`, or `None`."""
        stmt = select(ItemImportModel).where(
            ItemImportModel.id == import_id,
            owned_by(ItemImportModel, scope.user_id),
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return None if model is None else _to_domain(model)

    async def list_for_owner(self, *, scope: ContentFilter) -> list[ItemImport]:
        """Return the imports within `scope`, newest first."""
        stmt = (
            select(ItemImportModel)
            .where(owned_by(ItemImportModel, scope.user_id))
            .order_by(ItemImportModel.id.desc())
        )
        return [_to_domain(m) for m in (await self._session.execute(stmt)).scalars()]

    async def list_with_status(self, status: ImportStatus) -> list[ItemImport]:
        """Return everyone's imports with `status`, oldest first."""
        stmt = (
            select(ItemImportModel)
            .where(ItemImportModel.status == status.value)
            .order_by(ItemImportModel.queued_at, ItemImportModel.id)
        )
        return [_to_domain(m) for m in (await self._session.execute(stmt)).scalars()]

    async def recent_owners(self, limit: int) -> list[uuid.UUID]:
        """Return the owners of the `limit` imports started last, newest first."""
        stmt = (
            select(ItemImportModel.owner_id)
            .where(
                ItemImportModel.started_at.is_not(None),
                ItemImportModel.owner_id.is_not(None),
            )
            .order_by(ItemImportModel.started_at.desc(), ItemImportModel.id.desc())
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).scalars()
        return [owner for owner in rows if owner is not None]

    async def list_expired(self, before: datetime) -> list[ItemImport]:
        """Return everyone's imports that expired before `before`."""
        stmt = (
            select(ItemImportModel)
            .where(ItemImportModel.expires_at < before)
            .order_by(ItemImportModel.id)
        )
        return [_to_domain(m) for m in (await self._session.execute(stmt)).scalars()]
