"""The instance setup condition needed before executing jobs."""

from typing import Protocol


class SetupState(Protocol):
    """Expose setup completion without depending on the identity module."""

    async def is_complete(self) -> bool:
        """Return whether first-run setup has been completed."""
        ...
