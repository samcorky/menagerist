"""Read effective settings for other modules, with a short per-process cache."""

from time import monotonic
from typing import TYPE_CHECKING, cast
from uuid import UUID

import structlog

from app.modules.settings.application.resolution import is_valid
from app.modules.settings.domain.setting import SettingScope, resolve

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.modules.settings.domain.setting import SettingValue
    from app.modules.settings.ports.settings_catalogue import SettingsCatalogue
    from app.modules.settings.ports.unit_of_work import SettingsUnitOfWork
    from app.shared_kernel.settings import SettingKey

logger = structlog.get_logger()

type Address = tuple[SettingScope, UUID | None]


class CachedSettingsReader:
    """Resolve keys from the pin, the saved row, then the default.

    Saved rows are cached for `ttl` seconds per owner, so a job or request does not
    read the database for every setting. A write invalidates this process at once and
    others (the worker) within the TTL. A saved value that no longer validates is
    ignored, logged, and replaced by the default; it never fails the reader.
    """

    def __init__(
        self,
        catalogue: SettingsCatalogue,
        uow: Callable[[], SettingsUnitOfWork],
        *,
        ttl: float = 5.0,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self._catalogue = catalogue
        self._uow = uow
        self._ttl = ttl
        self._clock = clock
        self._cache: dict[Address, tuple[float, dict[str, SettingValue]]] = {}

    def invalidate(self) -> None:
        """Forget every cached row, so the next read sees the database."""
        self._cache.clear()

    async def get[T](self, key: SettingKey[T], *, user_id: UUID | None = None) -> T:
        """Return the effective value as the type the setting reads as."""
        descriptor = self._catalogue.descriptor(key.key)
        pin = self._catalogue.pin(key.key)
        if pin is not None:
            return cast("T", self._catalogue.to_python(key.key, pin.value))
        if descriptor.scope is SettingScope.USER and user_id is None:
            msg = f"{key.key} is user-scoped: pass user_id"
            raise ValueError(msg)
        owner = user_id if descriptor.scope is SettingScope.USER else None
        stored = (await self._rows((descriptor.scope, owner))).get(key.key)
        valid = stored is not None and is_valid(self._catalogue, key.key, stored)
        if stored is not None and not valid:
            logger.warning("stored setting is invalid; using the default", key=key.key)
        resolved = resolve(
            descriptor,
            pin=None,
            stored=stored,
            is_valid=lambda _: valid,
        )
        return cast("T", self._catalogue.to_python(key.key, resolved.value))

    async def _rows(self, address: Address) -> dict[str, SettingValue]:
        cached = self._cache.get(address)
        if cached is not None and self._clock() - cached[0] < self._ttl:
            return cached[1]
        scope, owner = address
        async with self._uow() as repos:
            rows = {
                k: r.value for k, r in (await repos.values.list(scope, owner)).items()
            }
        self._cache[address] = (self._clock(), rows)
        return rows
