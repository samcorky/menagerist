from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.modules.system.domain.release import UpdateCheck


class InMemoryUpdateCheckStore:
    """Keeps release-check results in a dict, for tests."""

    def __init__(self) -> None:
        self.checks: dict[str, UpdateCheck] = {}

    async def get(self, key: str) -> UpdateCheck | None:
        """Return the stored result for `key`, if there is one."""
        return self.checks.get(key)

    async def save(self, key: str, check: UpdateCheck) -> None:
        """Replace the result for `key`."""
        self.checks[key] = check
