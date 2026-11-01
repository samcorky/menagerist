"""A shared execution reservation that conflicts with instance restoration."""

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from contextlib import AbstractAsyncContextManager


class RestoreGuard(Protocol):
    """Reserve execution for its full lifetime without waiting for a restore."""

    def try_hold(self) -> AbstractAsyncContextManager[bool]:
        """Yield whether execution is reserved; release the reservation on exit."""
        ...
