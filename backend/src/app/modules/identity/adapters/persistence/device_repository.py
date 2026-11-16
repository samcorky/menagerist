from typing import TYPE_CHECKING

import structlog
from sqlalchemy import CursorResult, delete, select

from app.modules.identity.adapters.persistence.models import DeviceModel
from app.modules.identity.domain.device import Device

if TYPE_CHECKING:
    import uuid
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


def _to_domain(model: DeviceModel) -> Device:
    """Convert an ORM row into the domain entity."""
    return Device(
        id=model.id,
        user_id=model.user_id,
        token_hash=model.token_hash,
        created_at=model.created_at,
        last_seen_at=model.last_seen_at,
        expires_at=model.expires_at,
        user_agent=model.user_agent,
        platform=model.platform,
        mobile=model.mobile,
        name=model.name,
    )


def _to_model(device: Device) -> DeviceModel:
    """Convert a domain entity into its ORM row."""
    return DeviceModel(
        id=device.id,
        user_id=device.user_id,
        token_hash=device.token_hash,
        created_at=device.created_at,
        last_seen_at=device.last_seen_at,
        expires_at=device.expires_at,
        user_agent=device.user_agent,
        platform=device.platform,
        mobile=device.mobile,
        name=device.name,
    )


class SqlAlchemyDeviceRepository:
    """Postgres-backed `DeviceRepository`, scoped to one session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, device: Device) -> None:
        """Add a new device."""
        logger.debug("adding device", device_id=device.id)
        self._session.add(_to_model(device))
        await self._session.flush()

    async def save(self, device: Device) -> None:
        """Persist changes to an existing device."""
        await self._session.merge(_to_model(device))
        await self._session.flush()

    async def get(self, device_id: uuid.UUID) -> Device | None:
        """Return the device with `device_id`, or `None`."""
        model = await self._session.get(DeviceModel, device_id)
        return None if model is None else _to_domain(model)

    async def get_by_token_hash(self, token_hash: str) -> Device | None:
        """Return the device with `token_hash`, or `None`."""
        stmt = select(DeviceModel).where(DeviceModel.token_hash == token_hash)
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return None if model is None else _to_domain(model)

    async def list_for_user(self, user_id: uuid.UUID) -> list[Device]:
        """Return every device remembered for `user_id`."""
        stmt = select(DeviceModel).where(DeviceModel.user_id == user_id)
        models = (await self._session.execute(stmt)).scalars().all()
        return [_to_domain(m) for m in models]

    async def delete(self, device_id: uuid.UUID) -> None:
        """Forget one device; unknown ids are ignored."""
        await self._session.execute(
            delete(DeviceModel).where(DeviceModel.id == device_id)
        )

    async def delete_for_user(
        self, user_id: uuid.UUID, *, keep_id: uuid.UUID | None = None
    ) -> int:
        """Forget `user_id`'s devices except `keep_id`, returning how many went."""
        stmt = delete(DeviceModel).where(DeviceModel.user_id == user_id)
        if keep_id is not None:
            stmt = stmt.where(DeviceModel.id != keep_id)
        result = await self._session.execute(stmt)
        assert isinstance(result, CursorResult)
        return result.rowcount

    async def delete_expired(self, now: datetime) -> int:
        """Forget devices expired at `now`, returning how many went."""
        result = await self._session.execute(
            delete(DeviceModel).where(DeviceModel.expires_at <= now)
        )
        assert isinstance(result, CursorResult)
        return result.rowcount
