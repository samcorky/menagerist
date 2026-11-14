from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import uuid
    from datetime import datetime

    from app.modules.identity.domain.device import Device


class DeviceRepository(Protocol):
    """Access to remembered browsers, independent of storage backend."""

    async def add(self, device: Device) -> None:
        """Add a new device."""
        ...

    async def save(self, device: Device) -> None:
        """Persist changes to an existing device."""
        ...

    async def get(self, device_id: uuid.UUID) -> Device | None:
        """Return the device with `device_id`, or `None`."""
        ...

    async def get_by_token_hash(self, token_hash: str) -> Device | None:
        """Return the device with `token_hash`, or `None`."""
        ...

    async def list_for_user(self, user_id: uuid.UUID) -> list[Device]:
        """Return every device remembered for `user_id`."""
        ...

    async def delete(self, device_id: uuid.UUID) -> None:
        """Forget one device; unknown ids are ignored."""
        ...

    async def delete_for_user(
        self, user_id: uuid.UUID, *, keep_id: uuid.UUID | None = None
    ) -> int:
        """Forget `user_id`'s devices except `keep_id`, returning how many went."""
        ...

    async def delete_expired(self, now: datetime) -> int:
        """Forget devices expired at `now`, returning how many went."""
        ...
