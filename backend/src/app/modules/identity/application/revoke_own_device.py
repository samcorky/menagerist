import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.identity.domain.errors import CurrentSessionError, DeviceNotFoundError
from app.modules.identity.ports.unit_of_work import IdentityUnitOfWork
from app.shared_kernel.access import Access, OwnAccount
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True, frozen=True)
class RevokeOwnDeviceCommand:
    """Request to sign out and forget one of the calling user's devices."""

    device_id: uuid.UUID
    current_session_id: uuid.UUID


class RevokeOwnDevice(CommandHandler[IdentityUnitOfWork, RevokeOwnDeviceCommand, int]):
    """End every session on one of the user's devices and forget the device.

    Refused with `CurrentSessionError` for the device of the current session,
    and with `DeviceNotFoundError` if unknown or owned by another user.
    """

    access: ClassVar[Access] = OwnAccount()

    async def _handle(self, command: RevokeOwnDeviceCommand, actor: Actor) -> int:
        """Revoke the device if it belongs to `actor`, returning sessions ended."""
        async with self._uow as repos:
            device = await repos.devices.get(command.device_id)
            if device is None or device.user_id != actor.id:
                raise DeviceNotFoundError(f"Device {command.device_id} not found.")
            current = await repos.sessions.get(command.current_session_id)
            if current is not None and current.device_id == device.id:
                raise CurrentSessionError("Cannot revoke the current device.")
            ended = await repos.sessions.delete_for_device(device.id)
            await repos.devices.delete(device.id)
            await self._uow.commit()

        logger.info(
            "device revoked",
            user_id=actor.id,
            device_id=command.device_id,
            count=ended,
        )
        return ended
