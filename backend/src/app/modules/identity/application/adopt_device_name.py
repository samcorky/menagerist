import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.identity.application.list_device_name_suggestions import (
    find_name_suggestions,
)
from app.modules.identity.domain.device import Device
from app.modules.identity.domain.errors import DeviceNotFoundError
from app.modules.identity.ports.unit_of_work import IdentityUnitOfWork
from app.shared_kernel.access import Access, OwnAccount
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True, frozen=True)
class AdoptDeviceNameCommand:
    """Request to move an older device's name to the browser making the request."""

    current_session_id: uuid.UUID
    from_device_id: uuid.UUID


class AdoptDeviceName(
    CommandHandler[IdentityUnitOfWork, AdoptDeviceNameCommand, Device]
):
    """Give the current browser the name of an older device and forget that device.

    Only a device that `ListDeviceNameSuggestions` would offer can be adopted;
    anything else is refused with `DeviceNotFoundError`, so a request cannot
    remove a device in use, another kind of browser or another user's device.
    """

    access: ClassVar[Access] = OwnAccount()

    async def _handle(self, command: AdoptDeviceNameCommand, actor: Actor) -> Device:
        """Move the name across and remove the older device and its sessions."""
        async with self._uow as repos:
            found = await find_name_suggestions(
                repos,
                session_id=command.current_session_id,
                user_id=actor.id,
                now=datetime.now(UTC),
            )
            source = next(
                (d for d in found.candidates if d.id == command.from_device_id), None
            )
            if source is None or found.current is None:
                raise DeviceNotFoundError(
                    f"Device {command.from_device_id} cannot be reused."
                )
            found.current.rename(source.name)
            await repos.devices.save(found.current)
            await repos.sessions.delete_for_device(source.id)
            await repos.devices.delete(source.id)
            await self._uow.commit()

        logger.info(
            "device name reused",
            user_id=actor.id,
            device_id=found.current.id,
            replaced_device_id=source.id,
        )
        return found.current
