import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.identity.domain.device import Device
from app.modules.identity.domain.errors import DeviceNotFoundError
from app.modules.identity.ports.unit_of_work import IdentityUnitOfWork
from app.shared_kernel.access import Access, OwnAccount
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True, frozen=True)
class RenameOwnDeviceCommand:
    """Request to name, rename or clear the name of one of the user's devices."""

    device_id: uuid.UUID
    name: str | None


class RenameOwnDevice(
    CommandHandler[IdentityUnitOfWork, RenameOwnDeviceCommand, Device]
):
    """Give one of the calling user's devices a name.

    Refused with `DeviceNotFoundError` if the device is unknown or owned by
    another user, and with `InvalidDeviceNameError` if the name is too long.
    """

    access: ClassVar[Access] = OwnAccount()

    async def _handle(self, command: RenameOwnDeviceCommand, actor: Actor) -> Device:
        """Rename the device if it belongs to `actor`, returning it."""
        async with self._uow as repos:
            device = await repos.devices.get(command.device_id)
            if device is None or device.user_id != actor.id:
                raise DeviceNotFoundError(f"Device {command.device_id} not found.")
            device.rename(command.name)
            await repos.devices.save(device)
            await self._uow.commit()

        logger.info("device renamed", user_id=actor.id, device_id=device.id)
        return device
