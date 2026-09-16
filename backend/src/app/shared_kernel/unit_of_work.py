from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from types import TracebackType


class UnitOfWork[TRepos](Protocol):
    """Transaction boundary that yields a module's repository bundle."""

    async def __aenter__(self) -> TRepos:
        """Enter the transactional scope, returning the module's repositories."""
        ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Roll back on exception, then always release underlying resources."""
        ...

    async def commit(self) -> None:
        """Persist the changes made within this unit of work."""
        ...

    def on_commit(self, callback: Callable[[], Awaitable[None]]) -> None:
        """Register a side effect to run after this transaction commits."""
        ...


class JoinedUnitOfWork[TRepos]:
    """Runs a sub-handler against an already-open transaction."""

    def __init__(self, repos: TRepos, owner: UnitOfWork[TRepos]) -> None:
        self._repos = repos
        self._owner = owner

    async def __aenter__(self) -> TRepos:
        """Return the already-open repositories without starting a new transaction."""
        return self._repos

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """No-op: the owner handles rollback and cleanup."""

    async def commit(self) -> None:
        """No-op: the owner controls the commit."""

    def on_commit(self, callback: Callable[[], Awaitable[None]]) -> None:
        """Forward the callback to the owning unit of work."""
        self._owner.on_commit(callback)


class InMemoryUnitOfWork[TRepos]:
    """In-memory transaction boundary wrapping a repository bundle for tests."""

    def __init__(self, repos: TRepos) -> None:
        self._repos = repos
        self.committed = False
        self.rolled_back = False
        self._callbacks: list[Callable[[], Awaitable[None]]] = []

    async def __aenter__(self) -> TRepos:
        """Enter the transactional scope, returning the wrapped repositories."""
        return self._repos

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Record whether this unit of work exited due to an exception."""
        if exc_type is not None:
            self.rolled_back = True

    async def commit(self) -> None:
        """Record that this unit of work was committed and run deferred callbacks."""
        self.committed = True
        callbacks, self._callbacks = self._callbacks, []
        for callback in callbacks:
            await callback()

    def on_commit(self, callback: Callable[[], Awaitable[None]]) -> None:
        """Enqueue a callback to run when ``commit()`` is called."""
        self._callbacks.append(callback)
