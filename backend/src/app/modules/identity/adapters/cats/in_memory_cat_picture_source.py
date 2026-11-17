from collections import deque
from typing import TYPE_CHECKING

from app.modules.identity.domain.errors import CatServiceUnavailableError

if TYPE_CHECKING:
    from collections.abc import Iterable


class InMemoryCatPictureSource:
    """`CatPictureSource` for tests: hands out queued cats, then is unavailable."""

    def __init__(self, cats: Iterable[bytes] = ()) -> None:
        self._cats = deque(cats)

    async def fetch(self) -> bytes:
        """Return the next queued cat.

        Raises:
            CatServiceUnavailableError: Once the queue is empty.
        """
        if not self._cats:
            raise CatServiceUnavailableError("The cat service is not available.")
        return self._cats.popleft()
