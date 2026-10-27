"""Observable shared execution reservations without database infrastructure."""

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


class InMemoryRestoreGuard:
    """Let concurrent jobs share a reservation while restoration is unavailable."""

    def __init__(self, *, available: bool = True) -> None:
        self.available = available
        self.holders = 0

    @asynccontextmanager
    async def try_hold(self) -> AsyncIterator[bool]:
        """Track acquired reservations, including exceptional and cancelled exits."""
        acquired = self.available
        if acquired:
            self.holders += 1
        try:
            yield acquired
        finally:
            if acquired:
                self.holders -= 1
