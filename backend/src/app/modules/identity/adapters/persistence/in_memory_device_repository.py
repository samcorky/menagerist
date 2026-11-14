from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import uuid
    from datetime import datetime

    from app.modules.identity.domain.device import Device


class InMemoryDeviceRepository:
    """Dict-backed `DeviceRepository` for tests."""

    def __init__(self) -> None:
        self._devices: dict[uuid.UUID, Device] = {}

    async def add(self, device: Device) -> None:
        """Add a new device."""
        self._devices[device.id] = device

    async def save(self, device: Device) -> None:
        """Persist changes to an existing device."""
        self._devices[device.id] = device

    async def get(self, device_id: uuid.UUID) -> Device | None:
        """Return the device with `device_id`, or `None`."""
        return self._devices.get(device_id)

    async def get_by_token_hash(self, token_hash: str) -> Device | None:
        """Return the device with `token_hash`, or `None`."""
        return next(
            (d for d in self._devices.values() if d.token_hash == token_hash), None
        )

    async def list_for_user(self, user_id: uuid.UUID) -> list[Device]:
        """Return every device remembered for `user_id`."""
        return [d for d in self._devices.values() if d.user_id == user_id]

    async def delete(self, device_id: uuid.UUID) -> None:
        """Forget one device; unknown ids are ignored."""
        self._devices.pop(device_id, None)

    async def delete_for_user(
        self, user_id: uuid.UUID, *, keep_id: uuid.UUID | None = None
    ) -> int:
        """Forget `user_id`'s devices except `keep_id`, returning how many went."""
        kept = {
            i: d
            for i, d in self._devices.items()
            if d.user_id != user_id or i == keep_id
        }
        ended = len(self._devices) - len(kept)
        self._devices = kept
        return ended

    async def delete_expired(self, now: datetime) -> int:
        """Forget devices expired at `now`, returning how many went."""
        expired = [i for i, d in self._devices.items() if d.is_expired(now)]
        for device_id in expired:
            del self._devices[device_id]
        return len(expired)
