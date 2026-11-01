from typing import Protocol


class SetupGate(Protocol):
    """Read the first-run gate before accepting an anonymous upload."""

    async def is_open(self) -> bool:
        """Return whether no account exists; restore rechecks under the setup lock."""
        ...
