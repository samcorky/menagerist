from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from app.modules.system.domain.release import UpdateCheck


class UpdateCheckStore(Protocol):
    """The last release-check result for each source and channel."""

    async def get(self, key: str) -> UpdateCheck | None:
        """Return the stored result for `key`, if there is one."""
        ...

    async def save(self, key: str, check: UpdateCheck) -> None:
        """Replace the result for `key`, creating it on first use."""
        ...
