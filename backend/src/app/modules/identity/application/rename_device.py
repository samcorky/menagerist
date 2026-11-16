import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.identity.application.permissions import IdentityPermission
from app.modules.identity.domain.device import Device
from app.modules.identity.domain.errors import DeviceNotFoundError
from app.modules.identity.ports.unit_of_work import IdentityUnitOfWork
from app.shared_kernel.access import Access, Requires
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True, frozen=True)
class RenameDeviceCommand:
    """Request by an administrator to name, rename or clear any user's device."""

    device_id: uuid.UUID
    name: str | None


class RenameDevice(CommandHandler[IdentityUnitOfWork, RenameDeviceCommand, Device]):
    """Rename any user's device, for administrators who tidy or clear a name.

    Needs `identity:session:revoke`, the permission that already governs
    managing other people's devices.
    """

    access: ClassVar[Access] = Requires(IdentityPermission.REVOKE_SESSION)

    async def _handle(self, command: RenameDeviceCommand, actor: Actor) -> Device:
        """Rename the device, returning it.

        Raises:
            ForbiddenError: If `actor` lacks `identity:session:revoke`.
            DeviceNotFoundError: If the device does not exist.
            InvalidDeviceNameError: If the name is too long.
        """
        async with self._uow as repos:
            device = await repos.devices.get(command.device_id)
            if device is None:
                raise DeviceNotFoundError(f"Device {command.device_id} not found.")
            device.rename(command.name)
            await repos.devices.save(device)
            await self._uow.commit()

        logger.info(
            "device renamed",
            user_id=device.user_id,
            device_id=device.id,
            renamed_by=actor.id,
        )
        return device
