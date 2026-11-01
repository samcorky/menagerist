import asyncio
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from app.modules.system.adapters.platform.checks._util import observation
from app.modules.system.domain.readiness import CheckObservation, CheckStatus
from app.platform.storage_probe import DirectoryProbe, hint, probe_directory

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

_GIB = 1024**3


class StorageCheck:
    """Reports configured directory writability and available space."""

    def __init__(
        self,
        directories: Mapping[str, Path],
        *,
        min_free_bytes: int = _GIB,
        cache_ttl: timedelta = timedelta(seconds=60),
    ) -> None:
        self._directories = dict(directories)
        self._min_free_bytes = min_free_bytes
        self._cache_ttl = cache_ttl
        self._lock = asyncio.Lock()
        self._cached_at: datetime | None = None
        self._cached_probes: dict[str, DirectoryProbe] | None = None

    async def run(self) -> Mapping[str, CheckObservation]:
        """Probe configured directories and report each state and free space."""
        probes = await self._get_probes()
        now = datetime.now(UTC)
        result: dict[str, CheckObservation] = {}

        for name, probe in probes.items():
            path = self._directories[name]
            state_hint = hint(path, probe.state)
            result[f"storage:{name}Writable"] = observation(
                probe.state,
                "state",
                now=now,
                status=(
                    CheckStatus.PASS if probe.state == "writable" else CheckStatus.WARN
                ),
                output=state_hint,
            )
            if probe.free_bytes is None:
                continue

            free_gib = round(probe.free_bytes / _GIB, 2)
            is_low = probe.free_bytes < self._min_free_bytes
            low_space_hint = (
                f"{path} has only {free_gib:.2f} GiB free "
                + f"(minimum: {self._min_free_bytes / _GIB:.2f} GiB)."
                if is_low
                else None
            )
            result[f"storage:{name}FreeSpace"] = observation(
                free_gib,
                "GiB",
                now=now,
                status=CheckStatus.WARN if is_low else CheckStatus.PASS,
                output=low_space_hint,
            )

        return result

    async def _get_probes(self) -> dict[str, DirectoryProbe]:
        async with self._lock:
            now = datetime.now(UTC)
            if self._cached_at is not None and self._cached_probes is not None:
                age = now - self._cached_at
                if timedelta(0) <= age < self._cache_ttl:
                    return self._cached_probes

            probes = {
                name: await asyncio.to_thread(probe_directory, path)
                for name, path in self._directories.items()
            }
            self._cached_at = datetime.now(UTC)
            self._cached_probes = probes
            return probes
