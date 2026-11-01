"""PostgreSQL storage for saved setting values."""

from typing import TYPE_CHECKING

from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert

from app.modules.settings.adapters.persistence.models import SettingValueModel
from app.modules.settings.domain.setting import SettingScope, StoredSetting

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy import ColumnElement
    from sqlalchemy.ext.asyncio import AsyncSession


def _to_domain(model: SettingValueModel) -> StoredSetting:
    return StoredSetting(
        id=model.id,
        scope=SettingScope(model.scope),
        owner_id=model.owner_id,
        key=model.key,
        value=model.value,
        updated_at=model.updated_at,
        updated_by=model.updated_by,
    )


def _address(
    scope: SettingScope, owner_id: UUID | None, key: str
) -> list[ColumnElement[bool]]:
    owner = (
        SettingValueModel.owner_id.is_(None)
        if owner_id is None
        else SettingValueModel.owner_id == owner_id
    )
    return [SettingValueModel.scope == scope.value, owner, SettingValueModel.key == key]


class SqlAlchemySettingValueRepository:
    """Saved rows in `setting_values`, written as an upsert on their address."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(
        self, scope: SettingScope, owner_id: UUID | None, key: str
    ) -> StoredSetting | None:
        """Return the row, or nothing when no value has been saved."""
        model = await self._session.scalar(
            select(SettingValueModel)
            .where(*_address(scope, owner_id, key))
            .execution_options(populate_existing=True)
        )
        return _to_domain(model) if model is not None else None

    async def list(
        self, scope: SettingScope, owner_id: UUID | None
    ) -> dict[str, StoredSetting]:
        """Return every saved row for one owner, by key."""
        owner = (
            SettingValueModel.owner_id.is_(None)
            if owner_id is None
            else SettingValueModel.owner_id == owner_id
        )
        models = await self._session.scalars(
            select(SettingValueModel)
            .where(SettingValueModel.scope == scope.value, owner)
            .execution_options(populate_existing=True)
        )
        return {m.key: _to_domain(m) for m in models}

    async def save(self, row: StoredSetting) -> None:
        """Insert the row, or replace the value already saved at its address."""
        statement = insert(SettingValueModel).values(
            id=row.id,
            scope=row.scope.value,
            owner_id=row.owner_id,
            key=row.key,
            value=row.value,
            updated_at=row.updated_at,
            updated_by=row.updated_by,
        )
        replace = {
            "value": statement.excluded.value,
            "updated_at": statement.excluded.updated_at,
            "updated_by": statement.excluded.updated_by,
        }
        if row.owner_id is None:
            statement = statement.on_conflict_do_update(
                index_elements=["scope", "key"],
                index_where=text("owner_id IS NULL"),
                set_=replace,
            )
        else:
            statement = statement.on_conflict_do_update(
                index_elements=["owner_id", "key"],
                index_where=text("owner_id IS NOT NULL"),
                set_=replace,
            )
        await self._session.execute(statement)

    async def delete(
        self, scope: SettingScope, owner_id: UUID | None, key: str
    ) -> bool:
        """Remove a saved value; report whether one existed."""
        result = await self._session.execute(
            delete(SettingValueModel).where(*_address(scope, owner_id, key))
        )
        return bool(result.rowcount)  # type: ignore[attr-defined]
